"""The chat graph: a router sends each message to one specialist agent.

    START → router ─┬─ general ⇄ general_tools   (date/time, weather, web search)
                    ├─ company ⇄ company_tools   (company SQL)
                    └─ other                     (no tools: unclear or out-of-scope requests)
"""

from config import Settings
from core_llm.agents import add_agent
from core_llm.builder import build_llm
from core_llm.prompt import COMPANY_PROMPT, GENERAL_PROMPT, OTHER_PROMPT
from core_llm.router import ChatState, make_router, route_of
from core_llm.tools import GENERAL_TOOLS
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph


def build_graph(
    settings: Settings,
    checkpointer: BaseCheckpointSaver,
    company_tools: list[BaseTool],
) -> CompiledStateGraph:
    """`company_tools` need app resources (a DB pool), so the app builds and passes them."""
    llm = build_llm(settings)
    builder = StateGraph(ChatState)

    builder.add_node("router", make_router(llm))
    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", route_of, {"general": "general", "company": "company", "other": "other"})

    add_agent(builder, "general", llm, GENERAL_PROMPT, GENERAL_TOOLS)
    add_agent(builder, "company", llm, COMPANY_PROMPT, company_tools)
    add_agent(builder, "other", llm, OTHER_PROMPT, [])

    return builder.compile(checkpointer=checkpointer)
