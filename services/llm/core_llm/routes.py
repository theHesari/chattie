import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from core_llm import threads
from core_llm.auth import CurrentUserId
from core_llm.threads import THREAD_ID_PATTERN, ThreadAccessError
from core_llm.tracing import run_config


logger = logging.getLogger(__name__)
router = APIRouter(tags=["llm"])


class QueryRequest(BaseModel):
    query: str
    session_id: str | None = Field(default=None, pattern=THREAD_ID_PATTERN)
    tags: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    response: str
    session_id: str


@router.post("/query", summary="Query the LLM", response_model=QueryResponse)
async def query(request: Request, query_request: QueryRequest, user_id: CurrentUserId) -> QueryResponse:
    session_id = query_request.session_id or f"session-{uuid.uuid4()}"
    graph = request.app.state.graph

    try:
        await threads.touch(request.app.state.db_pool, session_id, user_id, query_request.query)
    except ThreadAccessError:
        raise HTTPException(status_code=404, detail="thread not found") from None

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(query_request.query)]},
            config=run_config(
                session_id,
                run_name="answer-question-base",
                user_id=user_id,
                tags=["base", *query_request.tags],
            ),
        )
    except Exception as exc:
        logger.exception("graph invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer = result["messages"][-1].content
    return QueryResponse(response=answer, session_id=session_id)
