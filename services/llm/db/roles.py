"""Login roles used by the API. Roles are cluster-wide, so this is idempotent and safe to re-run."""

from collections.abc import Mapping

import psycopg
from psycopg import sql

# role -> (password env var, extra attributes)
ROLES: dict[str, tuple[str, str]] = {
    "chattie_query": ("QUERY_DB_PASSWORD", ""),
    "chattie_app": ("APP_DB_PASSWORD", ""),
    "chattie_generator": ("GENERATOR_DB_PASSWORD", "BYPASSRLS"),
}


def ensure_roles(conn: psycopg.Connection, env: Mapping[str, str]) -> list[str]:
    """Create or update every role whose password variable is set; return their names.

    NOINHERIT and no memberships: no role can switch to another. A role whose password
    variable is missing is skipped, so later migrations that grant to it fail loudly.
    """
    done = []
    for role, (password_var, attributes) in ROLES.items():
        password = env.get(password_var)
        if not password:
            continue
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        conn.execute(
            sql.SQL("{} ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT {} PASSWORD {}").format(
                sql.SQL("ALTER" if exists else "CREATE"),
                sql.Identifier(role),
                sql.SQL(attributes),
                sql.Literal(password),
            )
        )
        done.append(role)
    return done
