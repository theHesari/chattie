"""Thread index: ownership and titles of chat threads.

LangGraph's checkpoint tables store serialized graph snapshots and aren't meant for
listing, so each thread also gets one plain row here: its owner, title and timestamps.
This table is the authority on who may read or continue a thread.
"""

from datetime import datetime

from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

TITLE_MAX_CHARS = 60
THREAD_ID_PATTERN = r"^[\w-]{1,128}$"  # mirrored in apps/web/lib/api/shared.ts

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS chat_threads (
        thread_id  TEXT PRIMARY KEY,
        title      TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # Ownership. Rows created before auth existed have no owner (NULL) until claimed
    # by the first account (see apps/web/lib/auth.ts).
    "ALTER TABLE chat_threads ADD COLUMN IF NOT EXISTS user_id TEXT",
    "DROP INDEX IF EXISTS chat_threads_updated_at_idx",
    "CREATE INDEX IF NOT EXISTS chat_threads_user_updated_idx ON chat_threads (user_id, updated_at DESC)",
)


class ThreadAccessError(Exception):
    """The thread exists but belongs to someone else."""


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


async def touch(pool: AsyncConnectionPool, thread_id: str, user_id: str, message: str) -> None:
    """Record activity on a thread, creating it for `user_id` if it's new.

    A new thread takes its title from its first message.
    Raises ThreadAccessError if the thread belongs to another user.
    """
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO chat_threads (thread_id, user_id, title) VALUES (%s, %s, %s)
            ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()
                WHERE chat_threads.user_id = EXCLUDED.user_id
            RETURNING thread_id
            """,
            (thread_id, user_id, make_title(message)),
        )
        if await cursor.fetchone() is None:
            raise ThreadAccessError(thread_id)


async def owner_of(pool: AsyncConnectionPool, thread_id: str) -> str | None:
    """Owner of a thread, or None if it doesn't exist (or predates auth and is unclaimed)."""
    async with pool.connection() as conn:
        cursor = await conn.execute("SELECT user_id FROM chat_threads WHERE thread_id = %s", (thread_id,))
        row = await cursor.fetchone()
        return row["user_id"] if row else None


async def list_recent(pool: AsyncConnectionPool, user_id: str, limit: int) -> list[ThreadSummary]:
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT thread_id AS id, title, updated_at FROM chat_threads
            WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s
            """,
            (user_id, limit),
        )
        return [ThreadSummary(**row) for row in await cursor.fetchall()]
