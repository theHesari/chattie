"""Invite codes for the invite-only platform.

Issue one (from services/llm, or `make invite EMAIL=person@example.com`):
    python -m db.invites create [--email person@example.com] [--days 14]
The code is printed once; only its SHA-256 hash is stored. The web app hashes the code the same way
and calls public.redeem_invite when the account is created.
"""

import argparse
import hashlib
import os
import secrets

import psycopg

from db.envfile import load_repo_env


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def create_invite(cur: psycopg.Cursor, *, email: str | None, created_by: str = "owner", ttl_days: int = 14) -> str:
    """Store a new invite and return its plain code (shown to the issuer once)."""
    code = secrets.token_urlsafe(16)
    cur.execute(
        "INSERT INTO public.invites (code_hash, email, created_by, expires_at) "
        "VALUES (%s, %s, %s, now() + make_interval(days => %s))",
        (hash_code(code), email.strip().lower() if email else None, created_by, ttl_days),
    )
    return code


def redeem_invite(conn: psycopg.Connection, code: str, email: str, used_by: str) -> bool:
    """Spend the code if it is valid. Mirrors what the web app does at sign-up."""
    return conn.execute("SELECT public.redeem_invite(%s, %s, %s)", (hash_code(code), email, used_by)).fetchone()[0]


def main() -> None:
    load_repo_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="issue a new invite code")
    create.add_argument("--email", help="restrict the code to this email address")
    create.add_argument("--days", type=int, default=14, help="days until it expires (default 14)")
    args = parser.parse_args()
    with psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"), port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"], dbname=os.environ.get("DB_NAME", "chattie"),
        autocommit=True,
    ) as conn, conn.cursor() as cur:
        code = create_invite(cur, email=args.email, ttl_days=args.days)
    print(f"invite code (shown once): {code}")
    print(f"valid for {args.days} days" + (f", only for {args.email}" if args.email else "") + "; give it to the person to enter on the sign-up page")


if __name__ == "__main__":
    main()
