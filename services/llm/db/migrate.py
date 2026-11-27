"""Numbered SQL migrations for the chattie database.

Each file in db/migrations/ is `<version>_<name>.sql`, applied in version order inside one
transaction and recorded in public.schema_migrations. Migrations never drop existing data.

Usage (from the repo root, see `make db-migrate`): python -m db.migrate
"""

import os
from pathlib import Path

import psycopg

from db.envfile import load_repo_env
from db.roles import ensure_roles

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
BASELINE = "0001"


def _company_exists(conn: psycopg.Connection) -> bool:
    return conn.execute("SELECT to_regclass('company.employees')").fetchone()[0] is not None


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; return the versions recorded by this call.

    A database that already has company.employees (created by the old setup script) adopts
    the baseline: it is recorded without being run, so existing data is never touched.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS public.schema_migrations ("
        " version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM public.schema_migrations")}
    recorded: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        version = path.stem.split("_")[0]
        if version in applied:
            continue
        with conn.transaction():
            if not (version == BASELINE and _company_exists(conn)):
                conn.execute(path.read_text())
            conn.execute("INSERT INTO public.schema_migrations (version) VALUES (%s)", (version,))
        recorded.append(version)
    return recorded


def main() -> None:
    load_repo_env()
    with psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=os.environ.get("DB_NAME", "chattie"),
        autocommit=True,
    ) as conn:
        roles = ensure_roles(conn, os.environ)
        print(f"roles ready: {', '.join(roles) or 'none'}")
        versions = apply_migrations(conn)
        print(f"applied: {', '.join(versions) or 'nothing (up to date)'}")


if __name__ == "__main__":
    main()
