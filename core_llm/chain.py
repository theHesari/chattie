from config import Settings
from core_llm.builder import build_llm
from core_llm.prompt import greeting_template
from core_llm.routes import router
from langchain_core.runnables import Runnable


def build_chain(settings: Settings) -> Runnable:
    llm = build_llm(settings)
    return greeting_template | llm


__all__ = ["build_chain", "router"]
