"""
Run:  uvicorn af_fastapi:app --port 8080 --reload

"""


import socket
from agent_framework import ChatMessage
from fastapi import FastAPI, HTTPException
from fastapi import FastAPI, Request, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import contextlib
import os
from pg_age_helper import PGAgeHelper
from dotenv import load_dotenv
from sse_bus import SESSIONS
from starlette.responses import StreamingResponse
import asyncio
from pydantic import BaseModel
import json
from typing import Any, Dict, List
from mcp_client import MCPClient
from openai import AzureOpenAI, AsyncAzureOpenAI   
from azure.identity.aio import (AzureDeveloperCliCredential,
                                DefaultAzureCredential,
                                AzureCliCredential,
                                get_bearer_token_provider)



from magentic_implementation_search import MagenticWorkflow
from handoff_implementation import  HandoffWorkflow
import logging
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger("uvicorn.error")

load_dotenv()
POD = socket.gethostname()
REV = os.getenv("CONTAINER_APP_REVISION", "v0.1")
GRAPH = "customer_graph"
DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)
MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "http://localhost:3000/mcp") # Dapr endpoint

aoai_endpoint    = os.getenv("ENDPOINT_URL",    "https://aihub6750316290.cognitiveservices.azure.com/")
aoai_deployment  = os.getenv("DEPLOYMENT_NAME", "gpt-4o")
aoai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
aoai_credential =  AzureCliCredential() # login with azd login # DefaultAzureCredential()
token_provider = get_bearer_token_provider(aoai_credential, "https://cognitiveservices.azure.com/.default")
aoai_client = AsyncAzureOpenAI(azure_endpoint=aoai_endpoint, azure_ad_token_provider=token_provider,
                               api_version=aoai_api_version)

print("Using DSN:", DSN["host"], DSN["port"], DSN["dbname"], DSN["user"])

system_message = """

You are a PostgreSQL AGE query generator. Your job is to produce correct, executable SQL that embeds Cypher for a CRM knowledge graph named customer_graph 
and call the tool query_using_sql_cypher to get results. Then use those results to inform further responses.

Only output code (one SQL statement per answer) unless asked otherwise.


Graph schema (labels, relationships, properties)

Node labels

Customer — properties are stored under payload:
payload.id, payload.name, payload.segment, payload.owner, payload.satisfaction_score, payload.health, payload.growth_potential, payload.current_arr, payload.current_mrr, payload.timezone, payload.notes

Contract — payload.id, payload.customer_id, payload.start_date, payload.end_date, payload.amount, payload.status, payload.auto_renew, payload.renewal_term_months, payload.last_renewal_date, payload.next_renewal_date

SupportCase — payload.id, payload.customer_id, payload.opened_at, payload.last_updated_at, payload.status, payload.priority, payload.escalation_level, payload.sla_breached, payload.product_area, payload.subject, payload.tags

Communication — payload.id, payload.customer_id, payload.timestamp, payload.channel, payload.counterpart, payload.direction, payload.sentiment, payload.summary

Opportunity — payload.id, payload.customer_id, payload.opp_type, payload.product, payload.stage, payload.amount, payload.opened_at, payload.expected_close

TelemetryMonth — payload.customer_id, payload.month, payload.dau, payload.mau, payload.feature_adoption, payload.usage_hours, payload.incidents

QBRArtifact — payload.customer_id, payload.report_period, payload.highlights, payload.risks, payload.asks, payload.attachments

Product(name), Feature(name) (catalog nodes)

Relationships

(:Customer)-[:ADOPTED_PRODUCT]->(:Product)

(:Customer)-[:HAS_CONTRACT]->(:Contract)

(:Customer)-[:RAISED_CASE]->(:SupportCase)

(:SupportCase)-[:ABOUT_AREA]->(:Feature)

(:Customer)-[:HAD_COMM]->(:Communication)

(:Customer)-[:HAS_OPPORTUNITY]->(:Opportunity)

(:Opportunity)-[:FOR_PRODUCT]->(:Product)

(:Customer)-[:HAS_TELEMETRY]->(:TelemetryMonth)

(:TelemetryMonth)-[:ADOPTED_FEATURE {percent, month}]->(:Feature)

(:Customer)-[:HAS_QBR]->(:QBRArtifact)

All business properties live under .payload. Access them as alias.payload.<field>.

Output format (SQL wrapper)

Always wrap Cypher in this shape and ensure the number of RETURN items equals the column list:
SELECT *
FROM ag_catalog.cypher('customer_graph', $$

  // Cypher goes here

$$) AS (
  col1 ag_catalog.agtype,
  col2 ag_catalog.agtype,
  -- etc.
);

Required conventions & gotchas

Use .payload for all business fields
Access properties as alias.payload.<field> (e.g., c.payload.name, ctr.payload.amount).

Keep rows with OPTIONAL MATCH
Use OPTIONAL MATCH for edges that might be missing to avoid dropping the base node.

Never filter an OPTIONAL MATCH with WHERE on the optional variable
A WHERE clause attached to an OPTIONAL MATCH that references the optional variable (e.g., WHERE sc.payload.status = 'open') will drop nulls and effectively turn it into an inner match.
Do this instead: compute flags in a WITH, then aggregate:

OPTIONAL MATCH (c)-[:RAISED_CASE]->(sc:SupportCase)
WITH c, sc, coalesce(sc.payload.status,'') AS sc_status
WITH c, sc, (sc IS NOT NULL AND sc_status IN ['open','Open','OPEN']) AS is_pending
WITH c,
     sum(CASE WHEN is_pending THEN 1 ELSE 0 END) AS open_cnt,
     collect(CASE WHEN is_pending THEN { id: sc.payload.id } ELSE NULL END) AS tmp
WITH c, open_cnt, [x IN tmp WHERE x IS NOT NULL] AS open_cases
RETURN ...


RETURN is terminal
Once you RETURN, the query ends. If you need further processing, use WITH (not RETURN) and keep piping until your single final RETURN.


Example working cypher queries:

User question:
I’m going on a sales call with customer 'Customer 080'” → Provide a consolidated customer insight including:

- Opportunities for upsell or cross-sell

Cypher Query:
SELECT *
FROM ag_catalog.cypher('customer_graph', $$

  MATCH (c:Customer)
  WHERE c.payload.name = 'Customer 080'

  OPTIONAL MATCH (c)-[:RAISED_CASE]->(sc:SupportCase)
  WITH c,
       collect(CASE WHEN sc IS NOT NULL AND (sc.payload.status = 'Open' OR sc.payload.status = 'Pending' OR sc.payload.status = 'In Progress' OR sc.payload.status = 'Escalated') THEN {
         case_id: sc.payload.id,
         status: sc.payload.status,
         priority: sc.payload.priority,
         opened_at: sc.payload.opened_at,
         last_updated_at: sc.payload.last_updated_at,
         escalation_level: sc.payload.escalation_level,
         sla_breached: coalesce(sc.payload.sla_breached, false),
         product_area: sc.payload.product_area,
         subject: sc.payload.subject,
         tags: sc.payload.tags
       } ELSE NULL END) AS open_cases_tmp,
       sum(CASE WHEN sc IS NOT NULL AND (sc.payload.status = 'Open' OR sc.payload.status = 'Pending' OR sc.payload.status = 'In Progress' OR sc.payload.status = 'Escalated') THEN 1 ELSE 0 END) AS open_case_count

  WITH c,
       coalesce(open_case_count, 0) AS open_case_count,
       [x IN open_cases_tmp WHERE x IS NOT NULL] AS open_cases

  OPTIONAL MATCH (c)-[:HAS_OPPORTUNITY]->(o:Opportunity)
  WITH c, open_case_count, open_cases,
       collect(CASE WHEN o IS NOT NULL AND (o.payload.opp_type = 'Upsell' OR o.payload.opp_type = 'Cross-sell') AND NOT (o.payload.stage = 'Closed Won' OR o.payload.stage = 'Closed Lost') THEN {
         opp_id: o.payload.id,
         opp_type: o.payload.opp_type,
         product: o.payload.product,
         stage: o.payload.stage,
         amount: coalesce(o.payload.amount, 0),
         opened_at: o.payload.opened_at,
         expected_close: o.payload.expected_close
       } ELSE NULL END) AS upsell_xsell_opps_tmp,
       sum(CASE WHEN o IS NOT NULL AND (o.payload.opp_type = 'Upsell' OR o.payload.opp_type = 'Cross-sell') AND NOT (o.payload.stage = 'Closed Won' OR o.payload.stage = 'Closed Lost') THEN coalesce(o.payload.amount, 0) ELSE 0 END) AS opp_total_amount,
       sum(CASE WHEN o IS NOT NULL AND (o.payload.opp_type = 'Upsell' OR o.payload.opp_type = 'Cross-sell') AND NOT (o.payload.stage = 'Closed Won' OR o.payload.stage = 'Closed Lost') THEN 1 ELSE 0 END) AS opp_count

  WITH c, open_case_count, open_cases,
       coalesce(opp_count, 0) AS opp_count,
       coalesce(opp_total_amount, 0) AS opp_total_amount,
       [x IN upsell_xsell_opps_tmp WHERE x IS NOT NULL] AS upsell_xsell_opps

  RETURN
    c.payload.id AS customer_id,
    c.payload.name AS customer_name,
    c.payload.segment AS segment,
    c.payload.owner AS owner,
    c.payload.health AS health,
    c.payload.satisfaction_score AS satisfaction_score,
    c.payload.current_arr AS current_arr,
    c.payload.current_mrr AS current_mrr,
    open_case_count AS open_case_count,
    open_cases AS open_cases,
    opp_count AS opp_count,
    opp_total_amount AS opp_total_amount,
    upsell_xsell_opps AS upsell_xsell_opps

$$) AS (
  customer_id ag_catalog.agtype,
  customer_name ag_catalog.agtype,
  segment ag_catalog.agtype,
  owner ag_catalog.agtype,
  health ag_catalog.agtype,
  satisfaction_score ag_catalog.agtype,
  current_arr ag_catalog.agtype,
  current_mrr ag_catalog.agtype,
  open_case_count ag_catalog.agtype,
  open_cases ag_catalog.agtype,
  opp_count ag_catalog.agtype,
  opp_total_amount ag_catalog.agtype,
  upsell_xsell_opps ag_catalog.agtype
);

Aggregation pattern (AGE-safe)





Do NOT use reduce(...).

Do NOT use list/pattern comprehensions that filter by property access (e.g., [x IN list WHERE x.payload.foo]).

Instead, compute booleans/derived scalars in a WITH, aggregate with SUM(CASE ...), and build lists with:

collect(CASE WHEN cond THEN { ... } ELSE NULL END) AS tmp
WITH [x IN tmp WHERE x IS NOT NULL] AS clean


Null safety

Numeric: coalesce(sum(...), 0)

Scalars: coalesce(field, default)

Booleans: coalesce(flag, false)

Case folding
AGE doesn’t support SQL lower(). Prefer exact string matches when you control casing. If normalization is needed, compute it in a WITH using toLower(field) and compare there (don’t attach it to OPTIONAL MATCH as a WHERE):

WITH c, sc, toLower(coalesce(sc.payload.status,'')) AS st
WITH c, sc, (st IN ['open','pending','escalated']) AS is_pending


Column list must match RETURN
The number and order of RETURN items must exactly match the AS ( ... ) column list in the SQL wrapper.

IDs

Internal node id: id(n)

Business id: n.payload.id

Close all blocks

Close map literals }

Close the $$ block before AS (...)

One SQL statement per answer

If asked for multiple sections (e.g., revenue + cases + opportunities), compute them in one Cypher with proper WITH pipelines and return all requested fields in one row per customer unless a list is explicitly requested.

Hard “don’ts”

Do NOT use reduce(...), list/pattern comprehensions with property access in filters, APOC procedures, or SQL functions like lower() inside Cypher.

Do NOT return a single map while declaring multiple columns (or vice versa).

Do NOT omit closing braces or ``` or the  $$/AS (...) wrapper. 
Do NOT add \n or other escape characters.


Use provided query_using_sql_cypher tool to execute the SQL you generate against the customer_graph and use the results to inform further responses.

"""


# ---- FastAPI app ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        #global pg_helper
        #pg_helper = await PGAgeHelper.create(DSN, GRAPH)
        yield
    finally:
        pass


app = FastAPI(title="AGE Node Creator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in prod
    allow_credentials=True,
    allow_methods=["GET","POST","OPTIONS"],
    allow_headers=["*"],
)


def _normalize_session_id(raw: str | None, default: str = "default") -> str:
    if not raw:
        return default
    return raw.split(",")[0].strip()


@app.get("/events")
async def sse_events(request: Request):
    sid = request.query_params.get("sid")  
    session_id = _normalize_session_id(sid)
    print(f"[@app.get(/events)] session={session_id} pod={POD} rev={REV}", flush=True)
    session = await SESSIONS.get_or_create(session_id)

    async def event_stream():
        # flush headers immediately (APIM/ACA friendly)
        yield "event: open\ndata: {}\n\n"

        heartbeat_every = 1.0  # seconds
        while True:
            if await request.is_disconnected():
                break
            try:
                # wait up to heartbeat interval for next message
                #msg = await asyncio.wait_for(session.q.get(), timeout=heartbeat_every)
                try:
                    msg = session.q.get_nowait()
                    print(f"[@app.get(/events)] MCP CLIENT SSE YIELD session={session_id} msg={msg}...", flush=True)
                except asyncio.QueueEmpty:
                    yield "event: noevent\ndata: {}\n\n"
                    await asyncio.sleep(heartbeat_every)
                    continue
                #msg = sse_event(payload, event="assistant")
                print(f"[@app.get(/events)] SSE YIELD {msg}")
                yield msg
                #await asyncio.sleep(5)
                #session.q.task_done()
            except asyncio.TimeoutError:
                # heartbeat (SSE comment doesn't disturb clients)
                yield "server version 1.0: ping\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )

# ---- Routes ----
@app.get("/health")
async def health():
    try:
        status = await pg_helper.health_check()
        if not status:
            raise HTTPException(status_code=500, detail="Database connection failed")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ConversationIn(BaseModel):
    user_query: str
    #client_id: str

async def call_mcp_tool(mcp_client, message):
    if getattr(message, "tool_calls", None):
        for tc in message.tool_calls:
            tool_name = tc.function.name
            tool_args = json.loads(tc.function.arguments)
            
            print(f"Calling tool: {tool_name} with args: {tool_args}")

            result = await mcp_client.session.call_tool(tool_name, tool_args)
            return result, tool_name, tool_args, tc.id
    return None, None, None, None


class SessionManager:
    """Keeps per-session, per-user chat histories."""
    def __init__(self) -> None:
        # sessions[session_id][user_id] -> list of messages (dicts or strings)
        self.sessions: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    def get_history(self, session_id: str, user_id: str) -> List[Dict[str, Any]]:
        return self.sessions.setdefault(session_id, {}).setdefault(user_id, [])

    def append(self, session_id: str, user_id: str, role: str, content: str) -> None:
        self.get_history(session_id, user_id).append({"role": role, "content": content})



# single, long-lived manager you reuse (e.g., module-level or injected)
session_manager = SessionManager()

async def handle_user_query(user_id: str, user_query: str, session_id: str) -> Dict[str, Any]:
    # Connect MCP
    mcp_cli = MCPClient(mcp_endpoint=MCP_ENDPOINT)
    mcp_cli.set_broadcast_session(session_id)
    await mcp_cli.connect(session_id=session_id)

    try:
        # Build available tool schema for the model
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.inputSchema,
                },
            }
            for t in mcp_cli.mcp_tools.tools
        ]
        print("Available tools:", available_tools)

        # Build message list from stored history + current user input
        history = session_manager.get_history(session_id, user_id)
        system_msg = {"role": "system", "content": system_message}
        msgs: List[Dict[str, Any]] = [system_msg, *history, {"role": "user", "content": user_query}]

        # First LLM call
        response = await aoai_client.chat.completions.create(
            model=aoai_deployment,
            messages=msgs,
            tools=available_tools,
            # Azure OpenAI Chat Completions uses `max_tokens`
            max_tokens=4000,
        )

        choice = response.choices[0]
        message = choice.message

        # Persist the user message once
        session_manager.append(session_id, user_id, "user", user_query)

        # Collect assistant text outputs (across potential tool call turns)
        final_text: List[str] = []

        # Safety: cap iterative tool-call loop
        for _ in range(16):
            # If no tool calls, this is a final assistant message; store and break
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                # message may be a dict or an SDK object; normalize
                content = (
                    message.get("content")
                    if isinstance(message, dict)
                    else getattr(message, "content", None)
                )
                if content:
                    final_text.append(content)
                    session_manager.append(session_id, user_id, "assistant", content)
                break

            # Otherwise, execute the tool(s) one-by-one (or your call_mcp_tool batches them)
            result, tool_name, tool_args, tc_id = await call_mcp_tool(mcp_cli, message)
            if result is None:
                # Model asked for a tool but we couldn’t execute; surface what we have and stop
                content = (
                    message.get("content")
                    if isinstance(message, dict)
                    else getattr(message, "content", None)
                )
                if content:
                    final_text.append(content)
                    session_manager.append(session_id, user_id, "assistant", content)
                break

            # Feed the tool result back
            # Ensure we keep using the same `msgs` list (not an undefined `messages`)
            msgs.extend(
                [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tc_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(tool_args),
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": getattr(result, "content", str(result)),
                    },
                ]
            )

            follow_up = await aoai_client.chat.completions.create(
                model=aoai_deployment,
                messages=msgs,
                tools=available_tools,
                max_tokens=4000,
            )
            follow_up_choice = follow_up.choices[0]
            message = follow_up_choice.message

        print(f"[handle_user_query] Final assistant text: {final_text}")
        return {"llm_response": final_text}

    finally:
        # Optional: close MCP connection if your client needs explicit cleanup
        with contextlib.suppress(Exception):
            await mcp_cli.close()

@app.post("/nodes")
async def create_node(item: dict) -> dict:
    """
    Create a node in DEFAULT_GRAPH and return: {"id", "label", "properties"}.
    Example payload:
    {
      "label": "TestNode",
      "properties": {"name": "hello", "nps": 42}
    }
    """
    print("Creating node with item:", item)
    node = await pg_helper.insert_node(payload_any=item, node_label=item["label"])
    return node



@app.post("/edges")
async def create_edge(edge: dict) -> dict:
    """
    Create an edge in DEFAULT_GRAPH and return: {"id", "label", "properties"}.
    Example parameters:
    {
        "from_label": "TestNode",
        "to_label": "TestNode",
        "edge_label": "TestEdge",
        "from_id": 1,
        "to_id": 2,
        "properties": {"relationship": "connected"}
    }
    """
    edge = await pg_helper.create_edge_by_ids(
        src_label=edge.get("from_label"),
        dst_label=edge.get("to_label"),
        edge_label=edge["edge_label"],
        src_id=edge["from_id"],
        dst_id=edge["to_id"],
        edge_payload=edge["properties"],
    )
    return edge

#@app.get("/nodes/{node_type}/{node_id}")
#async def find_nodes_by_type(node_type: str, node_id: str) -> list[dict]:
#    nodes = await pg_helper.find_out_by_types(src_label=node_type, src_id=node_id)
#    return nodes

@app.get("/nodes/{node_id}/all_edges")
async def find_nodes_by_type(node_id: str) -> list[dict]:
    #node = await pg_helper.find_specific_node(node_id=node_id)
    node = await pg_helper.find_specific_node_with_all_edges(node_id=node_id)
    return node




@app.get("/nodes")
async def get_nodes() -> list[dict]:
    nodes = await pg_helper.get_all_nodes_and_edges(limit=100)
    return nodes

def _ndjson(obj: dict) -> bytes:
    # newline-delimited JSON makes it easy for clients to parse incrementally
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")

@app.post("/conversation/{user_id}")
async def start_conversation(user_id: str, convo: ConversationIn, request: Request):
    if not user_id:
        return Response(content="user_id is required", status_code=400)

    orchestration_mode = request.query_params.get("mode", "handoff")
    print(f"orchestration_mode={orchestration_mode}")


    session_id = user_id  # keep your existing per-user session key
    logger.info(f"received [@app.post(/conversation/{user_id})] session={session_id} pod={POD} rev={REV} user_query={convo.user_query}")
    
    history = session_manager.get_history(session_id, user_id)
    user_message = ChatMessage(role="user", text=convo.user_query)
    history.append(user_message)

    if orchestration_mode == "magentic":
        workflow = MagenticWorkflow()
    else:
        workflow = HandoffWorkflow()
    

    #return StreamingResponse(
    #    magentic_workflow.run_workflow(history),
    #    media_type="application/x-ndjson",
    #    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    #)

    return StreamingResponse(
        workflow.run_workflow(history),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
   






#@app.post("/conversation/{user_id}")
async def start_conversation1(user_id: str, convo: ConversationIn, request: Request):
    if not user_id:
        return Response(content="user_id is required", status_code=400)

    session_id = user_id  # keep your existing per-user session key

    async def stream():
        # connect MCP once per streamed response
        try:
            mcp_cli = MCPClient(mcp_endpoint=MCP_ENDPOINT)
            mcp_cli.set_broadcast_session(session_id)
            await mcp_cli.connect(session_id=session_id)
        except Exception as e:
            yield _ndjson({"type": "error", "message": f"Failed to connect to MCP: {str(e)}"})
            return

        try:
            # build tools for the model from MCP discovery (same as your non-stream path)
            available_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                    },
                }
                for t in mcp_cli.mcp_tools.tools
            ]

            # reconstruct conversation history
            history = session_manager.get_history(session_id, user_id)
            system_msg = {"role": "system", "content": system_message}
            msgs = [system_msg, *history, {"role": "user", "content": convo.user_query}]
            session_manager.append(session_id, user_id, "user", convo.user_query)

            # let the client know we started
            yield _ndjson({"type": "start", "session": session_id})

            # up to N tool-call turns; each turn is a streamed model response
            for _ in range(16):
                # buffers for this streamed assistant turn
                text_chunks: list[str] = []
                tool_calls_buf: dict[int, dict] = {}  # idx -> {id, name, arguments}
                finish_reason: str | None = None

                # 1) stream assistant
                stream_resp = await aoai_client.chat.completions.create(
                    model=aoai_deployment,
                    messages=msgs,
                    tools=available_tools,
                    max_tokens=4000,
                    stream=True,  # <-- IMPORTANT
                )

                async for event in stream_resp:
                    # Azure Chat Completions streaming yields chunks with .choices
                    if not getattr(event, "choices", None):
                        continue
                    choice = event.choices[0]
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        # some chunks carry only finish_reason
                        finish_reason = choice.finish_reason or finish_reason
                        continue

                    # stream assistant content tokens as they arrive
                    if getattr(delta, "content", None):
                        text = delta.content
                        text_chunks.append(text)
                        yield _ndjson({"type": "content", "delta": text})

                    # assemble streamed tool calls (function name & arguments arrive in pieces)
                    if getattr(delta, "tool_calls", None):
                        for tc in delta.tool_calls:
                            idx = getattr(tc, "index", 0) or 0
                            buf = tool_calls_buf.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                            if getattr(tc, "id", None):
                                buf["id"] = tc.id
                            fn = getattr(tc, "function", None)
                            if fn is not None:
                                if getattr(fn, "name", None):
                                    buf["name"] += fn.name
                                if getattr(fn, "arguments", None):
                                    buf["arguments"] += fn.arguments

                    # keep finish_reason when present
                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason

                # persist this assistant turn (text part only) into your history
                if text_chunks:
                    session_manager.append(session_id, user_id, "assistant", "".join(text_chunks))

                # if there were tool calls, execute them, stream the results, then continue loop
                if tool_calls_buf:
                    # Let client know which tools are being invoked
                    yield _ndjson({
                        "type": "tool_calls",
                        "calls": [
                            {"index": idx, "id": call.get("id"), "name": call.get("name")}
                            for idx, call in sorted(tool_calls_buf.items())
                        ]
                    })

                    # execute each call and feed result back to the model
                    for idx, call in sorted(tool_calls_buf.items()):
                        name = call.get("name") or ""
                        raw_args = call.get("arguments") or "{}"
                        call_id = call.get("id") or f"tool_{idx}"
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            # stream a warning and skip call if arguments are malformed
                            yield _ndjson({"type": "warning", "message": f"Malformed tool args for {name}: {raw_args}"})
                            args = {}

                        # run the MCP tool
                        yield _ndjson({"type": "tool_start", "id": call_id, "name": name})
                        result = await mcp_cli.session.call_tool(name, args)
                        tool_content = getattr(result, "content", str(result))

                        # stream tool result to client
                        yield _ndjson({"type": "tool_result", "id": call_id, "content": tool_content})

                        # add assistant tool_call + tool result messages into msgs
                        msgs.extend([
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {"name": name, "arguments": json.dumps(args)},
                                    }
                                ],
                            },
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": tool_content,
                            },
                        ])

                    # after tools, loop again to get the assistant’s follow-up (streamed)
                    continue

                # no tool calls -> we’re done after this assistant turn
                break

            yield _ndjson({"type": "done"})
        finally:
            with contextlib.suppress(Exception):
                await mcp_cli.close()

    # NDJSON (one JSON object per line). If you prefer SSE, set media_type="text/event-stream"
    return StreamingResponse(stream(), media_type="application/x-ndjson")