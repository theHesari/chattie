"""Router node: decides which specialist agent handles the user's latest message."""

import logging
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

from core_llm.prompt import ROUTER_PROMPT, chat_prompt
from core_llm.ui_stream import HIDDEN_FROM_CHAT

logger = logging.getLogger(__name__)

Route = Literal["general", "company", "other"]
DEFAULT_ROUTE: Route = "general"
CONTEXT_MESSAGES = 6  # recent turns the router sees, for follow-up questions


class ChatState(MessagesState):
    route: Route


class RouteDecision(BaseModel):
    route: Route
    reason: str = Field(description="One short sentence explaining the choice.")


def _conversation(messages: list[BaseMessage]) -> list[BaseMessage]:
    """User turns and the assistant's text replies only: tool calls and results add nothing
    to the decision, and a tool result without its call would be an invalid prompt."""
    turns = [
        m for m in messages
        if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and m.content and not m.tool_calls)
    ]
    return turns[-CONTEXT_MESSAGES:]


def make_router(llm: BaseChatModel):
    # function_calling, not json_schema: when LangGraph streams this call, json_schema attaches
    # the parsed object to the streamed message and Pydantic warns on every turn.
    classifier = (
        chat_prompt(ROUTER_PROMPT) | llm.with_structured_output(RouteDecision, method="function_calling")
    ).with_config(run_name="router", tags=[HIDDEN_FROM_CHAT])

    async def router(state: ChatState) -> dict:
        # Never fail the chat over routing: on any problem the general agent still replies.
        try:
            decision: RouteDecision | None = await classifier.ainvoke(
                {"messages": _conversation(state["messages"])}
            )
        except Exception:
            logger.exception("routing failed; using %r", DEFAULT_ROUTE)
            return {"route": DEFAULT_ROUTE}
        if decision is None:  # the model answered without calling the classifier function
            logger.warning("router returned no decision; using %r", DEFAULT_ROUTE)
            return {"route": DEFAULT_ROUTE}
        logger.info("route=%s (%s)", decision.route, decision.reason)
        return {"route": decision.route}

    return router


def route_of(state: ChatState) -> Route:
    return state["route"]
