# magentic_implementation.py
from agent_framework import (
    ChatAgent,
    HostedCodeInterpreterTool,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticBuilder,
    MagenticFinalResultEvent,
    MagenticOrchestratorMessageEvent,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient, AzureOpenAIResponsesClient
from azure.identity.aio import AzureCliCredential
import json
from enum import Enum
from dataclasses import dataclass, asdict, is_dataclass

credential = AzureCliCredential()  # OK to create globally

def _json_default(o):
    # Make dataclasses, Enums, and bytes JSON-serializable
    if is_dataclass(o):
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

async def run_magentic_workflow(question: str):
    # make these locals, not module globals
    last_stream_agent_id: str | None = None
    stream_line_open = False
    output: str | None = None

    # 🔑 fetch token on the running loop
    token = await credential.get_token("https://cognitiveservices.azure.com/.default")

    # build agents/manager with the fresh token
    researcher_agent = ChatAgent(
        name="ResearcherAgent",
        description="Specialist in research and information gathering",
        instructions="You are a Researcher. You find information without additional computation or quantitative analysis.",
        chat_client=AzureOpenAIChatClient(ad_token=token.token),
    )
    coder_agent = ChatAgent(
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        chat_client=AzureOpenAIResponsesClient(ad_token=token.token),
        tools=HostedCodeInterpreterTool(),
    )
    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher_agent, coder=coder_agent)
        .with_standard_manager(
            chat_client=AzureOpenAIChatClient(ad_token=token.token),
            max_round_count=10,
            max_stall_count=3,
            max_reset_count=2,
        )
        .build()
    )

    try:
        async for event in workflow.run_stream(question):
            if isinstance(event, MagenticOrchestratorMessageEvent):
                resp = ResponseMessage(type="MagenticOrchestratorMessageEvent", delta=f"\n[ORCH:{event.kind}]\n\n{getattr(event.message, 'text', '')}\n{'-' * 26}")
                yield _ndjson({"response_message": resp})
            elif isinstance(event, MagenticAgentDeltaEvent):
                if last_stream_agent_id != event.agent_id or not stream_line_open:
                    if stream_line_open:
                        resp = ResponseMessage(type="MagenticAgentDeltaEvent", delta=" (incomplete)\n")
                        yield _ndjson({"response_message": resp})
                        #yield _ndjson({"type": "content", "delta": "\n"})
                    last_stream_agent_id = event.agent_id
                    stream_line_open = True
                    yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentDeltaEvent", delta=f"\n[STREAM:{event.agent_id}]: ")})
                if event.text:
                    yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentDeltaEvent", delta=event.text)})
            elif isinstance(event, MagenticAgentMessageEvent):
                if stream_line_open:
                    stream_line_open = False
                    yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentMessageEvent", delta=" (final)\n")})
                msg = event.message
                if msg is not None:
                    response_text = (msg.text or "").replace("\n", " ")
                    yield _ndjson({"response_message": ResponseMessage(type="MagenticAgentMessageEvent", delta=f"\n[AGENT:{event.agent_id}] {msg.role.value}\n\n{response_text}\n{'-' * 26}")})
            elif isinstance(event, MagenticFinalResultEvent):
                if event.message is not None:
                    yield _ndjson({"response_message": ResponseMessage(type="MagenticFinalResultEvent", delta=event.message.text)})

            elif isinstance(event, WorkflowOutputEvent):
                output = str(event.data) if event.data is not None else None
                
                yield _ndjson({"response_message": ResponseMessage(type="WorkflowOutputEvent", delta=f"Workflow output event: {output}")})
        if stream_line_open:
            stream_line_open = False


        yield _ndjson({"response_message": ResponseMessage(type="done", result=output)})
    except Exception as e:
        yield _ndjson({"type": "error", "message": f"Workflow execution failed: {e}"})
