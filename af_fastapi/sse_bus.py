import asyncio, json, os, logging
from typing import Dict, Optional
import redis.asyncio as aioredis

logger = logging.getLogger("uvicorn.error")

JSONRPC = "2.0"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def sse_event(data: dict, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Redis connection (lazy singleton) ────────────────────────────────────────
_redis_pool: Optional[aioredis.Redis] = None

async def _get_redis() -> aioredis.Redis:
    """Return a shared Redis connection pool (created on first call)."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


def _channel_name(session_id: str) -> str:
    return f"sse:{session_id}"


# ── Session: local queue fed by a Redis subscription ─────────────────────────
class Session:
    """
    Each SSE listener creates a Session. It subscribes to the Redis channel
    for the given session_id and relays messages into a local asyncio.Queue
    so the StreamingResponse generator can yield them.
    """
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.q: asyncio.Queue[str] = asyncio.Queue()
        self.closed = False
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None

    async def start_listening(self) -> None:
        """Subscribe to the Redis channel and pump messages into self.q."""
        r = await _get_redis()
        self._pubsub = r.pubsub()
        await self._pubsub.subscribe(_channel_name(self.session_id))
        self._listener_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        try:
            async for raw_msg in self._pubsub.listen():
                if self.closed:
                    break
                if raw_msg["type"] == "message":
                    await self.q.put(raw_msg["data"])
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Redis listener error for session {self.session_id}: {e}")

    async def close(self) -> None:
        self.closed = True
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._pubsub:
            await self._pubsub.unsubscribe(_channel_name(self.session_id))
            await self._pubsub.aclose()
            self._pubsub = None


# ── SessionManager: publish goes to Redis, subscribe is per-listener ─────────
class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> Session:
        """Get an existing local session or create one with a Redis subscription."""
        async with self._lock:
            s = self._sessions.get(session_id)
            if s is None or s.closed:
                s = Session(session_id)
                await s.start_listening()
                self._sessions[session_id] = s
            return s

    async def publish(self, session_id: str, msg: str) -> None:
        """Publish to Redis — all nodes subscribed to this session_id receive it."""
        r = await _get_redis()
        await r.publish(_channel_name(session_id), msg)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            s = self._sessions.pop(session_id, None)
        if s:
            await s.close()
            return True
        return False

    async def exists(self, session_id: str) -> bool:
        async with self._lock:
            return session_id in self._sessions

    async def close_all(self) -> None:
        """Shutdown hook: close all local subscriptions."""
        async with self._lock:
            for s in self._sessions.values():
                await s.close()
            self._sessions.clear()
        if _redis_pool:
            await _redis_pool.aclose()


SESSIONS = SessionManager()

# Optional: map user_id -> session_id for actor lookups
_USER_SESSION: Dict[str, str] = {}

def associate_user_session(user_id: str, session_id: str) -> None:
    if user_id and session_id:
        _USER_SESSION[user_id] = session_id

def session_for_user(user_id: str) -> Optional[str]:
    return _USER_SESSION.get(user_id)

# Convenience publishers
async def publish_progress(session_id: str, token: str, progress: float) -> None:
    payload = {
        "jsonrpc": JSONRPC,
        "method": "notifications/progress",
        "params": {"progressToken": token, "progress": float(progress)},
    }
    print(f"Publishing progress update: {payload}")
    await SESSIONS.publish(session_id, sse_event(payload, event="progress"))

async def publish_message(session_id: str, text: str, level: str = "info", extra: dict | None = None) -> None:
    payload = {
        "jsonrpc": JSONRPC,
        "method": "notifications/message",
        "params": {
            "level": level,
            "data": [{"type": "text", "text": text}],
        },
    }
    if extra:
        payload["params"].update(extra)
    print(f"Publishing message: {payload}")
    await SESSIONS.publish(session_id, sse_event(payload, event="assistant"))

async def publish_mcplog(session_id: str, text: str, level: str = "info") -> None:
    payload = {
        "jsonrpc": JSONRPC,
        "method": "notifications/mcplog",
        "params": {
            "level": level,
            "text": text,
        },
    }
    print(f"Publishing mcplog: {payload}")
    await SESSIONS.publish(session_id, sse_event(payload, event="mcplog"))


# ── Elicitation: push to browser, await user response ────────────────────────
_PENDING_ELICITATIONS: Dict[str, asyncio.Future] = {}

async def publish_elicitation(
    session_id: str,
    elicitation_id: str,
    message: str,
    options: list[str],
    provided: str | None = None,
) -> str | None:
    """Publish an elicitation event to the browser and wait for the user to respond.
    Returns the user's chosen value, or None if they cancel/timeout."""
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str | None] = loop.create_future()
    _PENDING_ELICITATIONS[elicitation_id] = future

    payload = {
        "jsonrpc": JSONRPC,
        "method": "elicitation/create",
        "params": {
            "elicitationId": elicitation_id,
            "message": message,
            "options": options,
            "provided": provided,
        },
    }
    await SESSIONS.publish(session_id, sse_event(payload, event="elicitation"))

    try:
        # Wait up to 60 seconds for user to respond
        result = await asyncio.wait_for(future, timeout=60.0)
        return result
    except asyncio.TimeoutError:
        logger.warning(f"Elicitation {elicitation_id} timed out after 60s")
        return provided  # fall back to provided value on timeout
    finally:
        _PENDING_ELICITATIONS.pop(elicitation_id, None)


def resolve_elicitation(elicitation_id: str, value: str | None) -> bool:
    """Called by the HTTP endpoint when the user responds. Returns True if resolved."""
    future = _PENDING_ELICITATIONS.get(elicitation_id)
    if future and not future.done():
        future.set_result(value)
        return True
    return False