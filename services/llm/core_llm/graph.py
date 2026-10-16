from config import Settings
from core_llm.builder import build_llm
from core_llm.prompt import greeting_template
from core_llm.tools import TOOLS, format_now
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition


def build_graph(settings: Settings, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    chain = greeting_template | build_llm(settings).bind_tools(TOOLS)

    async def agent(state: MessagesState) -> dict:
        reply = await chain.ainvoke({
            "messages": state["messages"],
            "current_datetime": format_now(),
        })
        return {"messages": [reply]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)
