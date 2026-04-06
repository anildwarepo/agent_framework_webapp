# magentic_implementation.py
import asyncio
from agent_framework import (
    ChatAgent,
    ChatContext,
    ChatMessage,
    ChatMiddleware,
    HostedCodeInterpreterTool,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticBuilder,
    MagenticFinalResultEvent,
    MagenticOrchestratorMessageEvent,
    WorkflowOutputEvent,
    MCPStreamableHTTPTool
)
from agent_framework.azure import AzureOpenAIChatClient, AzureOpenAIResponsesClient
from azure.identity.aio import DefaultAzureCredential
from mcp_client import LoggingMCPStreamableHTTPTool
import json
from enum import Enum
from dataclasses import dataclass, asdict, is_dataclass
from agent_framework import ChatMessageStore
from typing import Any, Awaitable, Callable, List, Optional
import time
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Monkey-patch: sanitize empty JSON-Schema sub-schemas (`{}`) that some
# models (e.g. gpt-oss-120b) reject.  Bare `list` fields in Pydantic
# produce `"items": {}` which triggers:
#   "JSON Schema not supported: could not understand the instance `{}`."
# ---------------------------------------------------------------------------
_SCHEMA_VALUED_KEYS = frozenset({
    "items", "additionalProperties", "contains",
    "if", "then", "else", "not",
    "propertyNames", "unevaluatedItems", "unevaluatedProperties",
})

def _sanitize_schema(obj: Any, _key: str | None = None) -> Any:
    """Recursively replace bare `{}` sub-schema values that strict endpoints reject."""
    if isinstance(obj, dict):
        if obj == {} and _key in _SCHEMA_VALUED_KEYS:
            return {"type": "string"}
        return {k: _sanitize_schema(v, _key=k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_schema(item, _key=_key) for item in obj]
    return obj

from agent_framework.openai._chat_client import OpenAIBaseChatClient as _OAIBase

_original_chat_to_tool_spec = _OAIBase._chat_to_tool_spec

def _patched_chat_to_tool_spec(self, tools):  # type: ignore[override]
    specs = _original_chat_to_tool_spec(self, tools)
    return [_sanitize_schema(spec) for spec in specs]

_OAIBase._chat_to_tool_spec = _patched_chat_to_tool_spec  # type: ignore[assignment]
# ---------------------------------------------------------------------------

logger = logging.getLogger("uvicorn.error")
_aoai_api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
# Priority: Entra ID service principal first, API key fallback
try:
    credential = DefaultAzureCredential()
    _aoai_api_key = ""  # SP available, ignore API key
except Exception:
    credential = None
if not credential and not _aoai_api_key:
    logger.warning("Azure credentials not configured. Graph workflow (generic) will be unavailable.")
MCP_ENDPOINT = os.environ.get("MCP_ENDPOINT")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
GRAPH_NAME = os.environ.get("GRAPH_NAME", "")


print("Using MCP_ENDPOINT:", MCP_ENDPOINT)
print("Using AZURE_OPENAI_ENDPOINT:", AZURE_OPENAI_ENDPOINT)
print("Using AZURE_DEPLOYMENT_NAME:", AZURE_DEPLOYMENT_NAME)
print("Using GRAPH_NAME:", GRAPH_NAME)

if not MCP_ENDPOINT:
    raise ValueError("MCP_ENDPOINT environment variable must be set")
if not GRAPH_NAME:
    raise ValueError("GRAPH_NAME environment variable must be set")

def create_message_store():
    return ChatMessageStore()


def _read_instruction_file(file_name: str, graph_name: str) -> str:
    instructions_path = Path(__file__).resolve().parent / "agent_instructions" / file_name
    instructions = instructions_path.read_text(encoding="utf-8-sig")
    return instructions.replace("{{GRAPH_NAME}}", graph_name).replace("{GRAPH_NAME}", graph_name)


def _resolve_instruction_file(base_name: str, suffix: str, graph_name: str) -> str:
    """Try domain-specific file first (e.g., *_meetings_graph_v2_OSS_v1.md), fall back to generic."""
    instructions_dir = Path(__file__).resolve().parent / "agent_instructions"
    # Try domain-specific: CYPHER_QUERY_GENERATION_AGENT_meetings_graph_v2_OSS_v1.md
    domain_file = instructions_dir / f"{base_name}_{graph_name}{suffix}"
    if domain_file.exists():
        logger.info(f"Using domain-specific instructions: {domain_file.name}")
        return _read_instruction_file(domain_file.name, graph_name)
    # Fall back to generic: CYPHER_QUERY_GENERATION_AGENT_GENERIC_OSS_v1.md
    generic_file = f"{base_name}_GENERIC{suffix}"
    logger.info(f"Using generic instructions: {generic_file}")
    return _read_instruction_file(generic_file, graph_name)


import re as _re

def _sanitize_output(text: str) -> str:
    """Clean up OSS model output: fix Unicode, strip leaked metadata, remove object refs."""
    if not text:
        return text

    # 1. Replace fancy Unicode whitespace/punctuation with ASCII
    text = (text
        .replace("\u202f", " ")   # narrow no-break space
        .replace("\u00a0", " ")   # no-break space
        .replace("\u2003", " ")   # em space
        .replace("\u2002", " ")   # en space
        .replace("\u2011", "-")   # non-breaking hyphen
        .replace("\u2010", "-")   # hyphen
        .replace("\u2013", "-")   # en dash
        .replace("\u2014", "-")   # em dash
        .replace("\u2018", "'")   # left single quote
        .replace("\u2019", "'")   # right single quote
        .replace("\u201c", '"')   # left double quote
        .replace("\u201d", '"')   # right double quote
        .replace("\u2026", "...")  # ellipsis
        .replace("\u2190", "<-")  # left arrow
        .replace("\u2192", "->")  # right arrow
    )

    # 2. Strip CJK bracket citations with JSON: 【{...}】 or 〔{...}〕 or ã€...ã€'
    text = _re.sub(r'[\u3010\u3014]\s*\{[^}]*\}\s*[\u3011\u3015]', '', text)
    # Also handle the garbled versions: ã€{...}ã€' ã€[...]ã€'
    text = _re.sub(r'\u3010[^\u3011]*\u3011', '', text)
    text = _re.sub(r'\u3014[^\u3015]*\u3015', '', text)
    # Catch remaining ã€...ã€' patterns (entity refs, numbers, ellipsis)
    text = _re.sub(r'\u3010[^\u3011]{0,200}\u3011', '', text)

    # 3. Strip raw Python object references
    text = _re.sub(r'<agent_framework\._types\.\w+ object at 0x[0-9a-fA-F]+>', '', text)

    # 4. Strip leaked function/source metadata in parens or brackets
    text = _re.sub(r'\{"source"\s*:\s*"functions\.[^"]*"[^}]*\}', '', text)

    # 5. Clean up extra whitespace left behind
    text = _re.sub(r'  +', ' ', text)
    text = _re.sub(r'\n\n\n+', '\n\n', text)

    return text.strip()


# Keep backward compat alias
_sanitize_unicode = _sanitize_output


def _json_default(o):
    # Make dataclasses, Enums, and bytes JSON-serializable
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, bytes):
        return o.decode("utf-8", errors="replace")
    # Fallback: string representation
    return str(o)

def _ndjson(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, default=_json_default) + "\n").encode("utf-8")


@dataclass
class ResponseMessage:
    type: str
    delta: str | None = None
    message: str | None = None
    result: str | None = None


class LoggingChatMiddleware(ChatMiddleware):
    """Chat middleware that logs AI interactions."""

    async def process(
        self,
        context: ChatContext,
        next: Callable[[ChatContext], Awaitable[None]],
    ) -> None:
        # Pre-processing: Log before AI call
        print(f"[Chat Class] Sending {len(context.messages)} messages to AI")

        # Continue to next middleware or AI service
        await next(context)

        for i, message in enumerate(context.messages):
            content = message.text if message.text else str(message.contents)
            print(f"  Message {i + 1} ({message.role.value}): {content}")
        # Post-processing: Log after AI response
        print("[Chat Class] AI response received")

class GraphWorkflow():
    def __init__(self, graph_name: str | None = None, model_name: str | None = None, session_id: str | None = None):
        # stream state
        self._last_stream_agent_id: Optional[str] = None
        self._stream_line_open: bool = False
        self._output: Optional[str] = None

        # lazily populated runtime state
        self._access_token = None          
        self._graph_query_generator_agent = None      
        self._graph_query_validator_agent = None 
        self._graph_query_executor_agent = None 
        self._response_generator_agent = None           
        self._create_message_store = create_message_store
        self._graph_name = graph_name or GRAPH_NAME
        self._deployment_name = model_name or AZURE_DEPLOYMENT_NAME
        self._session_id = session_id


    async def logging_chat_middleware(
            context: ChatContext,
            next: Callable[[ChatContext], Awaitable[None]],
        ) -> None:
            """Chat middleware that logs AI interactions."""
            # Pre-processing: Log before AI call
            print(f"[Chat] Sending {len(context.messages)} messages to AI")

            # Continue to next middleware or AI service
            await next(context)

            # Post-processing: Log after AI response
            print("[Chat] AI response received")
    
    async def _get_fresh_token(self):
        """Fetch or refresh an access token (buffers 60s before expiry). Skipped when using API key."""
        if _aoai_api_key:
            return None
        now = int(time.time())
        logger.info(f"Fetching fresh token at time {now}")
        if self._access_token is None or (getattr(self._access_token, "expires_on", 0) - 60) <= now:
            self._access_token = await credential.get_token("https://cognitiveservices.azure.com/.default")
        return self._access_token

    def _chat_client_kwargs(self, token, **extra):
        """Build kwargs for AzureOpenAIChatClient depending on auth mode."""
        if _aoai_api_key:
            return dict(api_key=_aoai_api_key, endpoint=AZURE_OPENAI_ENDPOINT, deployment_name=self._deployment_name, **extra)
        return dict(ad_token=token.token, endpoint=AZURE_OPENAI_ENDPOINT, deployment_name=self._deployment_name, **extra)
    
    async def _ensure_clients(self):
        """Create agents and the workflow exactly once (or after token refresh if you choose)."""
        logger.info("Ensuring clients are created or refreshed")
        token = await self._get_fresh_token()
        graph_age_mcp_server = LoggingMCPStreamableHTTPTool(
            name="graph age mcp server",
            url=MCP_ENDPOINT,
            broadcast_session_id=self._session_id,
        ) 
        

        if self._graph_query_generator_agent is None or self._graph_query_validator_agent is None or self._graph_query_executor_agent is None or self._response_generator_agent is None:
            
            # Select instruction files based on model capability
            _is_oss = any(kw in (self._deployment_name or "").lower() for kw in ("oss", "llama", "phi", "mistral", "deepseek", "codestral"))
            _instr_suffix = "_OSS_v1.md" if _is_oss else "_v1.md"
            logger.info(f"Model '{self._deployment_name}' → instruction suffix: {_instr_suffix}")

            graph_query_generator_instructions = _resolve_instruction_file("CYPHER_QUERY_GENERATION_AGENT", _instr_suffix, self._graph_name)

            self._graph_query_generator_agent = ChatAgent(
                name="graph query generator agent",
                description="Graph query generator agent that can answer questions about the graph using a graph query tool.",
                instructions=graph_query_generator_instructions,
                chat_client=AzureOpenAIChatClient(**self._chat_client_kwargs(token)),
                #chat_message_store_factory=self._create_message_store,
                tools=graph_age_mcp_server
            )


            graph_query_validator_instructions = _resolve_instruction_file("CYPHER_QUERY_VALIDATION_AGENT", _instr_suffix, self._graph_name)

            self._graph_query_validator_agent = ChatAgent(
                name="graph_query_validator",
                description="Graph query validator agent that can validate and refine graph queries using a graph query tool.",
                instructions=graph_query_validator_instructions,
                chat_client=AzureOpenAIChatClient(**self._chat_client_kwargs(token)),
                #chat_message_store_factory=self._create_message_store,
                tools=graph_age_mcp_server
            )

            self._graph_query_executor_agent = ChatAgent(
                name="graph_query_executor_agent",
                description="Graph query executor agent that can execute graph queries using a graph query tool.",
                instructions="""
                You are a graph query executor agent. Your job is to execute the SQL queries generated by the graph query generator agent using the provided tool 'query_using_sql_cypher' and return the results.
                State the query that you received from the graph query generator agent before executing it.
                Do not modify the generated queries. Send them as-is to the tool.
                """,
                chat_client=AzureOpenAIChatClient(**self._chat_client_kwargs(token, temperature=0.0)),
                middleware=[LoggingChatMiddleware()],
                #chat_message_store_factory=self._create_message_store,
                tools=graph_age_mcp_server
            )


            self._response_generator_agent = ChatAgent(
                name="response_generator_agent",
                description="Final response agent that states the final response based on the results from the graph query executor agent. ",
                instructions="""
                You are a final responder to the user question based on the results obtained from the graph query executor agent.
                Respond only if there are results. Otherwise, state that no results were found.
                Be accurate and concise in your responses. 
                The response should use the results obtained from the graph query executor agent to answer the user's question.
                You only need to respond when the query results are available from the _graph_query_validator_agent.
                """,
                chat_client=AzureOpenAIChatClient(**self._chat_client_kwargs(token, temperature=0.0)),
                #chat_message_store_factory=self._create_message_store,

            )

            orchestration_manager_instructions = _read_instruction_file("ORCHESTRATION_MANAGER_INSTRUCTIONS_v1.md", self._graph_name)
            task_ledger_full_prompt = _read_instruction_file("TASK_LEDGER_FULL_PROMPT_v1.md", self._graph_name)

            logger.info("Building workflow with agents")
            self._workflow = (
                MagenticBuilder()
                .participants(
                    graph_query_generator_agent=self._graph_query_generator_agent,
                    graph_query_validator=self._graph_query_validator_agent, 
                    #graph_query_executor=self._graph_query_executor_agent, 
                    #response_generator=self._response_generator_agent
                    )
                .with_standard_manager(
                    instructions=orchestration_manager_instructions,
                    task_ledger_full_prompt=task_ledger_full_prompt,
                    final_answer_prompt=_read_instruction_file("FINAL_ANSWER_PROMPT_v1.md", self._graph_name),
                    chat_client=AzureOpenAIChatClient(**self._chat_client_kwargs(token, temperature=0.0)),
                    max_round_count=6,
                    max_stall_count=2,
                    max_reset_count=2,
                )
                .build()
            )
            logger.info("Workflow built successfully")

    async def run_workflow(self, chat_history: List[ChatMessage]):
        output = None
        try:
            await self._ensure_clients()
            logger.info(f"Running workflow with question: {chat_history[-1].text}")
            # local stream state per run
            self._last_stream_agent_id = None
            self._stream_line_open = False
            self._output = None

            # Prose-loop detector: track generator responses to break infinite loops
            _generator_prose_count = 0
            _last_generator_text = ""
            _generator_agent_id = "graph_query_generator_agent"

            async for event in self._workflow.run_stream(chat_history):
                if isinstance(event, MagenticOrchestratorMessageEvent):
                    resp = ResponseMessage(type="MagenticOrchestratorMessageEvent", delta=f"\n[ORCH:{event.kind}]\n\n{getattr(event.message, 'text', '')}\n{'-' * 26}")
                    yield _ndjson({"response_message": resp})
                elif isinstance(event, MagenticAgentDeltaEvent):
                    if self._last_stream_agent_id != event.agent_id or not self._stream_line_open:
                        if self._stream_line_open:
                            resp = ResponseMessage(type="MagenticAgentDeltaEvent", delta=" (incomplete)\n")
                            yield _ndjson({"response_message": resp})
                            #yield _ndjson({"type": "content", "delta": "\n"})
                        self._last_stream_agent_id = event.agent_id
                        self._stream_line_open = True
                        yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentDeltaEvent", delta=f"\n[STREAM:{event.agent_id}]: ")})
                    if event.text:
                        yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentDeltaEvent", delta=event.text)})
                elif isinstance(event, MagenticAgentMessageEvent):
                    if self._stream_line_open:
                        self._stream_line_open = False
                        yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentMessageEvent", delta=" (final)\n")})
                    msg = event.message
                    if msg is not None:
                        response_text = (msg.text or "").replace("\n", " ")
                        yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentMessageEvent", delta=f"\n[AGENT:{event.agent_id}] {msg.role.value}\n\n{response_text}\n{'-' * 26}")})

                        # --- Prose-loop circuit breaker ---
                        # Detect when the generator returns prose instead of FINAL_SQL.
                        # For OSS models this happens on EVERY call — the model interprets
                        # execution_result and writes a natural-language answer.
                        # Terminate immediately on first prose since it contains the correct data.
                        if event.agent_id and _generator_agent_id in str(event.agent_id):
                            gen_text = msg.text or ""
                            is_prose = "SELECT" not in gen_text and "FINAL_SQL" not in gen_text
                            if is_prose and len(gen_text.strip()) > 5:
                                _generator_prose_count += 1
                                logger.warning(f"Generator returned prose ({_generator_prose_count}x): {gen_text[:100]}...")
                                # Force-terminate on first prose — the answer is already in the text
                                logger.warning("Prose detected — force-terminating workflow with generator's answer")
                                forced_answer = _sanitize_output(gen_text.strip())
                                self._output = forced_answer
                                output = forced_answer
                                yield _ndjson({"response_message": ResponseMessage(type="WorkflowOutputEvent", delta=f"Workflow output event: {forced_answer}")})
                                yield _ndjson({"response_message": ResponseMessage(type="done", result=forced_answer)})
                                return
                            else:
                                _generator_prose_count = 0  # Reset if it returns SQL

                elif isinstance(event, MagenticFinalResultEvent):
                    if event.message is not None:
                        yield _ndjson({"response_message": ResponseMessage(type="WorkflowFinalResultEvent", delta=_sanitize_output(event.message.text or ""))})

                elif isinstance(event, WorkflowOutputEvent):
                    if event.data is None:
                        output = None
                    else:
                        raw = getattr(event.data, "text", None) or str(event.data)
                        output = _sanitize_output(raw)
                    self._output = output
                    chat_history.append(ChatMessage(role="assistant", text=output or ""))
                    yield _ndjson({"response_message": ResponseMessage(type="WorkflowOutputEvent", delta=f"Workflow output event: {output}")})
            if self._stream_line_open:
                self._stream_line_open = False

            final_output = self._output if self._output is not None else output
            yield _ndjson({"response_message": ResponseMessage(type="done", result=final_output)})
        except asyncio.CancelledError:
            logger.warning("Workflow stream cancelled (client disconnected).")
            return
        except BaseException as e:
            logger.exception("Workflow execution failed")
            error_message = f"Workflow execution failed: {e}"
            yield _ndjson({"response_message": ResponseMessage(type="error", message=error_message)})
            yield _ndjson({"response_message": ResponseMessage(type="done", result=self._output if self._output is not None else output)})



