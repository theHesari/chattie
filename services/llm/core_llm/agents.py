"""Specialist agent nodes: a system prompt plus the tools that route is allowed to use."""

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from core_llm.prompt import chat_prompt
from core_llm.router import ChatState
from core_llm.tools import format_now


def make_agent(llm: BaseChatModel, system_prompt: str, tools: list[BaseTool]):
    chain = chat_prompt(system_prompt) | (llm.bind_tools(tools) if tools else llm)

    async def agent(state: ChatState) -> dict:
        reply = await chain.ainvoke({"messages": state["messages"], "current_datetime": format_now()})
        return {"messages": [reply]}

    return agent


def add_agent(
    builder: StateGraph,
    name: str,
    llm: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
) -> None:
    """Adds `name` (and, if it has tools, its own `<name>_tools` loop) to the graph."""
    builder.add_node(name, make_agent(llm, system_prompt, tools))
    if not tools:
        builder.add_edge(name, END)
        return
    tool_node = f"{name}_tools"
    builder.add_node(tool_node, ToolNode(tools))
    builder.add_conditional_edges(name, tools_condition, {"tools": tool_node, END: END})
    builder.add_edge(tool_node, name)
