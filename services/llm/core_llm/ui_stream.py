"""Bridge between LangGraph and the Vercel AI SDK UI message stream protocol (v1).

Spec: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
Every event is one SSE `data:` line holding a JSON chunk; the stream ends with `[DONE]`.
Tools are sent as *dynamic* tools so the frontend needs no tool type definitions.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

UI_MESSAGE_STREAM_HEADERS = {
    "cache-control": "no-cache",
    "x-vercel-ai-ui-message-stream": "v1",
    "x-accel-buffering": "no",
}

AGENT_NODE = "agent"
TOOLS_NODE = "tools"


def _sse(chunk: dict[str, Any]) -> str:
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")


async def stream_ui_messages(
    graph: CompiledStateGraph,
    inputs: dict[str, Any],
    config: RunnableConfig,
) -> AsyncIterator[str]:
    """Run the graph and yield its output as UI message stream SSE events.

    Text comes token by token from `messages` mode; tool calls and results come
    from `updates` mode, once each agent / tools node has finished.
    """
    text_id: str | None = None

    def close_text() -> str | None:
        nonlocal text_id
        if text_id is None:
            return None
        event, text_id = _sse({"type": "text-end", "id": text_id}), None
        return event

    yield _sse({"type": "start", "messageId": str(uuid.uuid4())})
    yield _sse({"type": "start-step"})
    try:
        async for mode, payload in graph.astream(inputs, config, stream_mode=["messages", "updates"]):
            if mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") != AGENT_NODE or not isinstance(chunk, AIMessageChunk):
                    continue
                if delta := _text(chunk.content):
                    if text_id is None:
                        text_id = str(uuid.uuid4())
                        yield _sse({"type": "text-start", "id": text_id})
                    yield _sse({"type": "text-delta", "id": text_id, "delta": delta})
                continue

            for node, update in payload.items():
                messages = (update or {}).get("messages", [])
                if node == AGENT_NODE:
                    if event := close_text():
                        yield event
                    for message in messages:
                        for call in getattr(message, "tool_calls", []):
                            yield _sse({
                                "type": "tool-input-available",
                                "toolCallId": call["id"],
                                "toolName": call["name"],
                                "input": call["args"],
                                "dynamic": True,
                            })
                    yield _sse({"type": "finish-step"})
                elif node == TOOLS_NODE:
                    for message in messages:
                        if message.status == "error":
                            yield _sse({"type": "tool-output-error", "toolCallId": message.tool_call_id,
                                        "errorText": _text(message.content), "dynamic": True})
                        else:
                            yield _sse({"type": "tool-output-available", "toolCallId": message.tool_call_id,
                                        "output": _text(message.content), "dynamic": True})
                    yield _sse({"type": "start-step"})
    except Exception:
        logger.exception("chat stream failed")
        if event := close_text():
            yield event
        yield _sse({"type": "error", "errorText": "The assistant failed to respond. Please try again."})
    yield _sse({"type": "finish"})
    yield "data: [DONE]\n\n"


def to_ui_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Convert stored LangGraph messages into AI SDK `UIMessage` objects.

    One user turn -> one user message; everything the graph produced until the next
    user turn (model calls, tool calls, tool results) -> one assistant message.
    """
    ui_messages: list[dict[str, Any]] = []
    tool_parts: dict[str, dict[str, Any]] = {}

    for message in messages:
        if isinstance(message, HumanMessage):
            ui_messages.append({
                "id": message.id,
                "role": "user",
                "parts": [{"type": "text", "text": _text(message.content)}],
            })
        elif isinstance(message, AIMessage):
            if not ui_messages or ui_messages[-1]["role"] != "assistant":
                ui_messages.append({"id": message.id, "role": "assistant", "parts": []})
            parts = ui_messages[-1]["parts"]
            parts.append({"type": "step-start"})
            if text := _text(message.content):
                parts.append({"type": "text", "text": text, "state": "done"})
            for call in message.tool_calls:
                part = {
                    "type": "dynamic-tool",
                    "toolName": call["name"],
                    "toolCallId": call["id"],
                    "state": "input-available",
                    "input": call["args"],
                }
                tool_parts[call["id"]] = part
                parts.append(part)
        elif isinstance(message, ToolMessage) and (part := tool_parts.get(message.tool_call_id)):
            if message.status == "error":
                part.update(state="output-error", errorText=_text(message.content))
            else:
                part.update(state="output-available", output=_text(message.content))

    return ui_messages
