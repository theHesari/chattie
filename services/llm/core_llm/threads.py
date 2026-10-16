"""Thread index for the chat sidebar.

LangGraph's checkpoint tables store serialized graph snapshots and aren't meant for
listing, so each thread also gets one plain row here: its title and timestamps.
"""

from datetime import datetime

from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

TITLE_MAX_CHARS = 60

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS chat_threads (
        thread_id  TEXT PRIMARY KEY,
        title      TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS chat_threads_updated_at_idx ON chat_threads (updated_at DESC)",
)


class ThreadSummary(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    title: str
    updated_at: datetime


def make_title(first_message: str) -> str:
    title = " ".join(first_message.split())
    return title if len(title) <= TITLE_MAX_CHARS else title[: TITLE_MAX_CHARS - 1].rstrip() + "…"


async def setup(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        for statement in _SCHEMA:
            await conn.execute(statement)


async def touch(pool: AsyncConnectionPool, thread_id: str, message: str) -> None:
    """Record activity on a thread; a new thread takes its title from its first message."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO chat_threads (thread_id, title) VALUES (%s, %s)
            ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()
            """,
            (thread_id, make_title(message)),
        )


async def list_recent(pool: AsyncConnectionPool, limit: int) -> list[ThreadSummary]:
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT thread_id AS id, title, updated_at FROM chat_threads ORDER BY updated_at DESC LIMIT %s",
            (limit,),
        )
        return [ThreadSummary(**row) for row in await cursor.fetchall()]
