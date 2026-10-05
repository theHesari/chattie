from config import Settings
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver


def build_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
    )


def build_memory(settings: Settings) -> InMemorySaver:
    return InMemorySaver()
