"""A restorable dump of the shared company world, and a guarded restore.

The dump holds data only, for the `company` schema, and only the seeded world: generated characters,
their simulated teams and everything they own are left out. Restore applies the migrations first (so
structure, permissions and policies come from one place) and then loads the data. It never touches the
`auth` or `public` schemas. Uses pg_dump and pg_restore from PG_BIN.
"""

import os
import secrets
import subprocess
import tempfile
from pathlib import Path

import psycopg
from psycopg import sql

from company.generator import clear_world
from db.migrate import apply_migrations
from db.pgtools import pg_tool
from db.roles import ensure_roles

DUMP_ARGS = ["--data-only", "-Fc", "-n", "company", "--exclude-table-data=company.leave_policy"]


class RestoreRefused(Exception):
    """The target already holds a world and the caller did not confirm replacing it."""


def _run(tool: str, args: list[str], params: dict) -> None:
    env = {**os.environ, "PGHOST": str(params["host"]), "PGPORT": str(params["port"]),
           "PGUSER": params["user"], "PGPASSWORD": params["password"]}
    done = subprocess.run([str(pg_tool(tool)), *args], env=env, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"{tool} failed: {done.stderr.strip()[-600:]}")


def _admin(params: dict) -> psycopg.Connection:
    return psycopg.connect(**{**params, "dbname": "postgres"}, autocommit=True)


def dump_world(params: dict, out: Path) -> None:
    """Write the seeded world of the database in `params` (host, port, user, password, dbname) to `out`."""
    scratch = f"chattie_dump_{secrets.token_hex(4)}"
    with tempfile.TemporaryDirectory() as tmp, _admin(params) as admin:
        full = Path(tmp) / "full.dump"
        _run("pg_dump", [*DUMP_ARGS, "-f", str(full), params["dbname"]], params)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch)))
        try:
            scratch_params = {**params, "dbname": scratch}
            with psycopg.connect(**scratch_params, autocommit=True) as conn:
                apply_migrations(conn)
            _run("pg_restore", ["--data-only", "--disable-triggers", "-d", scratch, str(full)], params)
            with psycopg.connect(**scratch_params, autocommit=True) as conn:
                generated = "(SELECT id FROM company.employees WHERE origin <> 'seed')"
                conn.execute(
                    f"DELETE FROM company.orders WHERE sales_rep_id IN {generated} OR customer_id IN "
                    f"(SELECT id FROM company.customers WHERE account_manager_id IN {generated})")
                conn.execute(f"DELETE FROM company.customers WHERE account_manager_id IN {generated}")
                conn.execute("DELETE FROM company.employees WHERE origin <> 'seed'")  # requests, days, events cascade
            out.parent.mkdir(parents=True, exist_ok=True)
            _run("pg_dump", [*DUMP_ARGS, "-f", str(out), scratch], params)
        finally:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (scratch,))
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(scratch)))


def restore_world(params: dict, dump: Path, *, confirm: bool) -> None:
    """Load the dump into the database in `params`. An empty world needs no confirmation; replacing an
    existing one (which deletes generated characters and the requests visitors filed) does."""
    with psycopg.connect(**params, autocommit=True) as conn:
        ensure_roles(conn, os.environ)
        apply_migrations(conn)
        if conn.execute("SELECT count(*) FROM company.employees").fetchone()[0]:
            characters = conn.execute("SELECT count(*) FROM company.employees WHERE origin <> 'seed'").fetchone()[0]
            requests = conn.execute("SELECT count(*) FROM company.employee_requests").fetchone()[0]
            if not confirm:
                raise RestoreRefused(
                    f"restoring would delete the existing world: {characters} generated characters/teammates "
                    f"and all {requests} requests. Pass confirm=True to go ahead.")
            clear_world(conn)
    _run("pg_restore", ["--data-only", "--disable-triggers", "-d", params["dbname"], str(dump)], params)
