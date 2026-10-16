import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from core_llm.tracing import run_config


logger = logging.getLogger(__name__)
router = APIRouter(tags=["llm"])


class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None
    user_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    response: str
    session_id: str


@router.post("/query", summary="Query the LLM", response_model=QueryResponse)
async def query(request: Request, query_request: QueryRequest) -> QueryResponse:
    session_id = query_request.session_id or f"session-{uuid.uuid4()}"
    graph = request.app.state.graph

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(query_request.query)]},
            config=run_config(
                session_id,
                run_name="answer-question-base",
                user_id=query_request.user_id,
                tags=["base", *query_request.tags],
            ),
        )
    except Exception as exc:
        logger.exception("graph invocation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer = result["messages"][-1].content
    return QueryResponse(response=answer, session_id=session_id)
