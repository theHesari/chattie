"""What every authenticated call does about the caller's character: bring it back if archived, note
that the user is active (at most once an hour), and keep it and the world up to date."""

from datetime import date

from psycopg_pool import ConnectionPool

from company.catchup import catch_up_character, catch_up_world
from company.characters import CharacterOut, reactivate


def ensure_character(pool: ConnectionPool, user_id: str, today: date) -> CharacterOut | None:
    """The caller's active character, or None if they have none. Synchronous (run it in a thread)."""
    with pool.connection() as conn:
        character = reactivate(conn, user_id=user_id, today=today)
        if character is None:
            return None
        touched = conn.execute(
            "UPDATE company.employees SET last_active_at = now() WHERE id = %s "
            "AND (last_active_at IS NULL OR last_active_at < now() - interval '1 hour') RETURNING id",
            (character.employee_id,)).fetchone()
        if touched:  # the hourly beat: also the moment to catch the character and the world up
            catch_up_character(conn, character.employee_id, today)
            catch_up_world(conn, today)
        return character
