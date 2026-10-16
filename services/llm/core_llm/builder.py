from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from config import Settings
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


def build_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
    )


@asynccontextmanager
async def build_db_pool(settings: Settings) -> AsyncIterator[AsyncConnectionPool]:
    """Postgres pool shared by the LangGraph checkpointer and the thread index."""
    pool = AsyncConnectionPool(
        settings.DATABASE_CONNINFO,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    async with pool:
        yield pool


async def build_memory(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    return checkpointer
