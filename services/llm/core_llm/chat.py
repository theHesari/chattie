from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from core_llm import threads
from core_llm.auth import CurrentUserId
from core_llm.threads import THREAD_ID_PATTERN, ThreadAccessError, ThreadSummary
from core_llm.tracing import run_config
from core_llm.ui_stream import UI_MESSAGE_STREAM_HEADERS, stream_ui_messages, to_ui_messages

router = APIRouter(tags=["chat"])


class UIMessagePart(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    text: str | None = None


class UserUIMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    role: Literal["user"]
    parts: list[UIMessagePart]

    @property
    def text(self) -> str:
        return "".join(part.text or "" for part in self.parts if part.type == "text")


class ChatRequest(BaseModel):
    """Body sent by the web app: the thread id and only the newest user message.

    Earlier messages are already stored in the LangGraph checkpointer.
    """

    id: str = Field(pattern=THREAD_ID_PATTERN)
    message: UserUIMessage


def _thread_not_found() -> HTTPException:
    # Same answer for "doesn't exist" and "not yours", so ids can't be probed.
    return HTTPException(status_code=404, detail="thread not found")


@router.post("/chat", summary="Stream a reply (AI SDK UI message stream protocol)")
async def chat(request: Request, body: ChatRequest, user_id: CurrentUserId) -> StreamingResponse:
    text = body.message.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="message has no text")

    try:
        await threads.touch(request.app.state.db_pool, body.id, user_id, text)
    except ThreadAccessError:
        raise _thread_not_found() from None

    stream = stream_ui_messages(
        request.app.state.graph,
        {"messages": [HumanMessage(text, id=body.message.id)]},
        run_config(body.id, run_name="chat-stream", user_id=user_id, tags=["chat"]),
    )
    return StreamingResponse(stream, media_type="text/event-stream", headers=UI_MESSAGE_STREAM_HEADERS)


@router.get("/threads", summary="The caller's most recently active threads, newest first")
async def list_threads(
    request: Request,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ThreadSummary]:
    return await threads.list_recent(request.app.state.db_pool, user_id, limit)


@router.get("/threads/{thread_id}/messages", summary="Stored messages of a thread, as AI SDK UIMessages")
async def thread_messages(
    request: Request,
    user_id: CurrentUserId,
    thread_id: Annotated[str, Path(pattern=THREAD_ID_PATTERN)],
) -> list[dict[str, Any]]:
    owner = await threads.owner_of(request.app.state.db_pool, thread_id)
    if owner is None:
        return []  # a new thread; never read checkpoints the index doesn't vouch for
    if owner != user_id:
        raise _thread_not_found()
    state = await request.app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})
    return to_ui_messages(state.values.get("messages", []))
