"""Build and maintain the company world (see company/generator.py).

Usage, from services/llm (or through the Makefile: `make db-world`, `make db-extend`):
    python -m db.company.setup world --as-of 2026-11-27 [--seed 42]
    python -m db.company.setup world --as-of 2026-11-27 --reset --confirm
    python -m db.company.setup extend --to 2026-12-31
    python -m db.company.setup archive [--days 30]
    python -m db.company.setup dump [--out db/company/dump/world.dump]
    python -m db.company.setup restore [--dump db/company/dump/world.dump] [--confirm]

Reads DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (the owner connection). `world` first creates the
roles and applies pending migrations. `--reset` deletes the whole company world, including generated
characters and the requests visitors filed, so it prints what would be lost and needs `--confirm`.
"""

import argparse
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

from company.characters import archive_inactive
from company.generator import advance_order_statuses, build_world, clear_world, extend_world
from company.snapshot import RestoreRefused, dump_world, restore_world
from db.envfile import load_repo_env
from db.migrate import apply_migrations
from db.roles import ensure_roles


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=os.environ.get("DB_NAME", "chattie"),
        autocommit=True,
    )


def _count(conn: psycopg.Connection, query: str) -> int:
    return conn.execute(query).fetchone()[0]


def cmd_world(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    ensure_roles(conn, os.environ)
    apply_migrations(conn)
    if _count(conn, "SELECT count(*) FROM company.employees"):
        characters = _count(conn, "SELECT count(*) FROM company.employees WHERE origin <> 'seed'")
        requests = _count(conn, "SELECT count(*) FROM company.employee_requests")
        if not args.reset:
            raise SystemExit("A world already exists. Use --reset --confirm to replace it, or `extend` to add days.")
        print(f"--reset would delete: {characters} generated characters/teammates and all {requests} requests.")
        if not args.confirm:
            raise SystemExit("Nothing deleted. Repeat with --confirm to go ahead.")
        clear_world(conn)
    stats = build_world(conn, seed=args.seed, as_of=args.as_of)
    print(f"built: {stats.employees} employees, {stats.orders} orders, {stats.requests} requests, "
          f"{stats.work_days} work days (as of {args.as_of}, seed {args.seed})")


def cmd_extend(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    stats = extend_world(conn, to=args.to)
    advanced = advance_order_statuses(conn, args.to)
    print(f"extended to {args.to}: +{stats.orders} orders, +{stats.work_days} work days; {advanced} order statuses advanced")


DEFAULT_DUMP = Path(__file__).with_name("dump") / "world.dump"


def connection_params() -> dict:
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "dbname": os.environ.get("DB_NAME", "chattie"),
    }


def cmd_archive(conn: psycopg.Connection, args: argparse.Namespace) -> None:
    today = args.today or datetime.now(ZoneInfo(os.environ.get("COMPANY_TIMEZONE") or "UTC")).date()
    count = archive_inactive(conn, today=today, days=args.days)
    print(f"archived {count} character(s) inactive for more than {args.days} days (as of {today})")


def cmd_dump(args: argparse.Namespace) -> None:
    dump_world(connection_params(), args.out)
    print(f"wrote the seeded world (no generated characters) to {args.out} ({args.out.stat().st_size // 1024} KB)")


def cmd_restore(args: argparse.Namespace) -> None:
    try:
        restore_world(connection_params(), args.dump, confirm=args.confirm)
    except RestoreRefused as refused:
        raise SystemExit(f"Nothing changed. {refused} Repeat with --confirm.") from None
    print(f"restored the world from {args.dump}")


def main() -> None:
    load_repo_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    world = commands.add_parser("world", help="build the world (creates roles, applies migrations first)")
    world.add_argument("--as-of", type=date.fromisoformat, required=True)
    world.add_argument("--seed", type=int, default=42)
    world.add_argument("--reset", action="store_true", help="delete an existing world first")
    world.add_argument("--confirm", action="store_true", help="really delete (with --reset)")
    extend = commands.add_parser("extend", help="append orders and work days up to a date")
    extend.add_argument("--to", type=date.fromisoformat, required=True)
    archive = commands.add_parser("archive", help="archive generated characters inactive for more than N days (run daily)")
    archive.add_argument("--days", type=int, default=30)
    archive.add_argument("--today", type=date.fromisoformat, default=None, help=argparse.SUPPRESS)
    dump = commands.add_parser("dump", help="write the seeded world (data only) to a file")
    dump.add_argument("--out", type=Path, default=DEFAULT_DUMP)
    restore = commands.add_parser("restore", help="load a dump (applies migrations first; never touches auth/public)")
    restore.add_argument("--dump", type=Path, default=DEFAULT_DUMP)
    restore.add_argument("--confirm", action="store_true", help="allow replacing an existing world")
    args = parser.parse_args()
    if args.command == "dump":
        return cmd_dump(args)
    if args.command == "restore":
        return cmd_restore(args)
    if args.command == "archive":  # runs as the generator role, not the owner
        with psycopg.connect(**{**connection_params(), "user": "chattie_generator",
                                "password": os.environ["GENERATOR_DB_PASSWORD"]}, autocommit=True) as conn:
            return cmd_archive(conn, args)
    with connect() as conn:
        {"world": cmd_world, "extend": cmd_extend}[args.command](conn, args)


if __name__ == "__main__":
    main()
