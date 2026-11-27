"""Keeping the world and persisted characters current as real time passes."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import psycopg
import pytest

from company.catchup import catch_up_character, catch_up_world
from company.characters import replace_character
from company.generator import world_checksum

AS_OF = date(2026, 11, 27)  # the session world's end (matches conftest.WORLD_AS_OF)


def scalar(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def test_stale_as_of_is_repaired_on_first_call(world_db, generator_conn):
    today = AS_OF + timedelta(days=40)
    assert catch_up_world(generator_conn, today) is True
    assert scalar(world_db, "SELECT value FROM company.meta WHERE key = 'as_of'") == today.isoformat()
    assert scalar(world_db, "SELECT max((ordered_at AT TIME ZONE 'UTC')::date) FROM company.orders") > AS_OF
    assert scalar(world_db, "SELECT max(day) FROM company.work_days") >= today - timedelta(days=3)


def test_second_call_the_same_day_does_nothing(world_db, generator_conn):
    today = AS_OF + timedelta(days=5)
    assert catch_up_world(generator_conn, today) is True
    checksum = world_checksum(world_db)
    assert catch_up_world(generator_conn, today) is False
    assert world_checksum(world_db) == checksum


def test_a_world_that_is_already_current_is_left_alone(world_db, generator_conn):
    assert catch_up_world(generator_conn, AS_OF) is False
    assert catch_up_world(generator_conn, AS_OF - timedelta(days=3)) is False  # a clock that runs behind


def test_two_concurrent_calls_run_the_work_once(world_db):
    today = AS_OF + timedelta(days=20)

    def call(_):
        with psycopg.connect(
            host=os.environ.get("DB_HOST", "localhost"), port=os.environ.get("DB_PORT", "5432"), user="chattie_generator",
            password=os.environ["GENERATOR_DB_PASSWORD"], dbname=world_db.info.dbname, autocommit=True,
        ) as conn:
            return catch_up_world(conn, today)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(call, range(2)))
    assert sorted(results) == [False, True]
    days = scalar(world_db, "SELECT count(*) FROM (SELECT employee_id, day FROM company.work_days GROUP BY 1, 2 HAVING count(*) > 1) d")
    assert days == 0  # nothing was written twice


@pytest.fixture
def manager(world_db, generator_conn):
    character = replace_character(generator_conn, user_id="u-mgr", display_name="Mgr", role="manager", department_id=2, today=AS_OF)
    team = [r[0] for r in world_db.execute("SELECT id FROM company.employees WHERE manager_id = %s AND origin = 'simulated' ORDER BY id", (character.employee_id,))]
    return character.employee_id, team


def test_character_work_days_reach_today_and_respect_approved_leave(world_db, generator_conn, manager):
    me, team = manager
    today = AS_OF + timedelta(days=10)  # Monday 7 Dec 2026
    leave = AS_OF + timedelta(days=4)  # Tuesday 1 Dec: filed after the character was built
    world_db.execute(
        "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, status, request_key) "
        "VALUES (%s, 'day_off', %s, %s, 'approved', gen_random_uuid())", (me, leave, leave))

    added = catch_up_character(generator_conn, me, today)

    assert added > 0
    for person in [me, *team]:
        assert scalar(world_db, "SELECT max(day) FROM company.work_days WHERE employee_id = %s", (person,)) == today
    assert scalar(world_db, "SELECT kind FROM company.work_days WHERE employee_id = %s AND day = %s", (me, leave)) == "leave"
    assert scalar(world_db, "SELECT count(*) FROM company.work_days WHERE employee_id = %s AND extract(isodow FROM day) >= 6", (me,)) == 0


def test_character_catch_up_is_idempotent(world_db, generator_conn, manager):
    me, _ = manager
    today = AS_OF + timedelta(days=10)
    catch_up_character(generator_conn, me, today)
    checksum = world_checksum(world_db)
    assert catch_up_character(generator_conn, me, today) == 0
    assert world_checksum(world_db) == checksum


def test_sales_orders_continue_without_duplicates(world_db, generator_conn, manager):
    me, team = manager
    before = scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id = ANY(%s)", (team,))
    catch_up_character(generator_conn, me, AS_OF + timedelta(days=60))
    after = scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id = ANY(%s)", (team,))
    assert after >= before
    assert scalar(world_db, "SELECT max((ordered_at AT TIME ZONE 'UTC')::date) FROM company.orders WHERE sales_rep_id = ANY(%s)", (team,)) <= AS_OF + timedelta(days=60)
    catch_up_character(generator_conn, me, AS_OF + timedelta(days=60))
    assert scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id = ANY(%s)", (team,)) == after


def test_catch_up_of_an_unknown_or_archived_character_adds_nothing(world_db, generator_conn):
    assert catch_up_character(generator_conn, 999_999, AS_OF + timedelta(days=5)) == 0


def test_catch_up_of_a_database_with_no_generated_world_does_nothing(world_db, generator_conn):
    """A database upgraded from the old sample data has people and orders but no meta row yet."""
    world_db.execute("DELETE FROM company.meta")
    assert catch_up_world(generator_conn, AS_OF + timedelta(days=30)) is False
