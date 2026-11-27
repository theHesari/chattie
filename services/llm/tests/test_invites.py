"""Invite codes: single use, expiry, optional email binding, stored hashed."""

import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from db.invites import create_invite, hash_code, redeem_invite
from db.migrate import apply_migrations


@pytest.fixture
def db(owner_conn):
    apply_migrations(owner_conn)
    owner_conn.execute("TRUNCATE public.invites")
    return owner_conn


def issue(conn, **kwargs) -> str:
    with conn.cursor() as cur:
        return create_invite(cur, created_by="test", **kwargs)


def test_hash_matches_the_sha256_hex_the_web_app_computes():
    assert hash_code("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_valid_code_redeems_exactly_once(db):
    code = issue(db, email=None)
    assert redeem_invite(db, code, "a@example.test", "user-1") is True
    assert redeem_invite(db, code, "a@example.test", "user-1") is False
    assert redeem_invite(db, code, "b@example.test", "user-2") is False


def test_unknown_code_fails(db):
    assert redeem_invite(db, "not-a-real-code", "a@example.test", "u") is False


def test_expired_code_fails(db):
    code = issue(db, email=None)
    db.execute("UPDATE public.invites SET expires_at = now() - interval '1 second'")
    assert redeem_invite(db, code, "a@example.test", "u") is False


def test_new_codes_last_14_days_by_default(db):
    issue(db, email=None)
    days = db.execute("SELECT extract(epoch FROM expires_at - created_at) / 86400 FROM public.invites").fetchone()[0]
    assert 13.99 < float(days) < 14.01


def test_email_bound_code_only_works_for_that_address_ignoring_case(db):
    code = issue(db, email="Ada@Example.test")
    assert redeem_invite(db, code, "other@example.test", "u") is False
    assert redeem_invite(db, code, "ADA@example.TEST", "u") is True


def test_only_the_hash_is_stored(db):
    code = issue(db, email=None)
    stored = " ".join(str(value) for row in db.execute("SELECT * FROM public.invites") for value in row)
    assert code not in stored and hash_code(code) in stored


def test_two_concurrent_redemptions_have_exactly_one_winner(db, test_db_name):
    code = issue(db, email=None)

    def attempt(i):
        with psycopg.connect(
            host=os.environ.get("DB_HOST", "localhost"), port=os.environ.get("DB_PORT", "5432"),
            user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"], dbname=test_db_name, autocommit=True,
        ) as conn:
            return redeem_invite(conn, code, "a@example.test", f"user-{i}")

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(True) == 1
