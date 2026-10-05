import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
router = APIRouter(tags=["llm"])

_chain = None
_handler = None


def _get_chain(settings):
    global _chain
    if _chain is None:
        from core_llm.chain import build_chain
        _chain = build_chain(settings)
    return _chain


def _get_handler():
    global _handler
    if _handler is None:
        from langfuse.langchain import CallbackHandler
        _handler = CallbackHandler()
    return _handler


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=10)
    session_id: str | None = None
    user_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    response: str
    session_id: str


@router.post("/query", summary="Query the LLM", response_model=QueryResponse)
async def query(request: Request, query_request: QueryRequest) -> QueryResponse:
    session_id = query_request.session_id or f"session-{uuid.uuid4()}"
    state = request.app.state
    chain = _get_chain(state.settings)
    handler = _get_handler()

    try:
        result = await chain.ainvoke(
            {"user_input": query_request.query},
            config={
                "callbacks": [handler],
                "run_name": "answer-question-base",
                "metadata": {
                    "langfuse_session_id": session_id,
                    "langfuse_user_id": query_request.user_id or "anonymous",
                    "langfuse_tags": ["api", "base", *query_request.tags],
                },
            },
        )
    except Exception as exc:
        logger.exception("base chain invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer = result.content if hasattr(result, "content") else str(result)
    return QueryResponse(response=answer, session_id=session_id)
