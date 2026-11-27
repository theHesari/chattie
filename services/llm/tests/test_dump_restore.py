"""Reproducible world: dump (seed data only) and guarded restore."""

import os
from datetime import date

import psycopg
import pytest

from company.characters import replace_character
from company.snapshot import RestoreRefused, dump_world, restore_world

TODAY = date(2026, 11, 27)


def scalar(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


@pytest.fixture
def dump_of_world_with_visitors(world_db, generator_conn, db_params, tmp_path):
    """A dump taken from a database that also holds a generated manager (with team) and an employee."""
    replace_character(generator_conn, user_id="u-mgr", display_name="Mgr", role="manager", department_id=2, today=TODAY)
    replace_character(generator_conn, user_id="u-emp", display_name="Emp", role="employee", department_id=2, today=TODAY)
    out = tmp_path / "world.dump"
    dump_world(db_params(world_db.info.dbname), out)
    return out


def test_dump_contains_no_visitor_or_simulated_rows(world_db, dump_of_world_with_visitors, scratch_db, db_params):
    target = scratch_db()
    restore_world(db_params(target), dump_of_world_with_visitors, confirm=False)
    with psycopg.connect(**db_params(target), autocommit=True) as restored:
        assert scalar(restored, "SELECT count(*) FROM company.employees WHERE origin <> 'seed'") == 0
        assert scalar(restored, "SELECT count(*) FROM company.employees") == 33
        assert scalar(restored, "SELECT count(*) FROM company.customers") == 60  # only the seeded customers
        for table in ("products", "holidays", "departments"):
            assert scalar(restored, f"SELECT count(*) FROM company.{table}") == scalar(world_db, f"SELECT count(*) FROM company.{table}")
        seed_orders = scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id IN (SELECT id FROM company.employees WHERE origin = 'seed')")
        assert scalar(restored, "SELECT count(*) FROM company.orders") == seed_orders
        assert scalar(restored, "SELECT value FROM company.meta WHERE key = 'as_of'") == scalar(world_db, "SELECT value FROM company.meta WHERE key = 'as_of'")


def test_restore_into_an_empty_database_then_permissions_hold(dump_of_world_with_visitors, scratch_db, db_params):
    target = scratch_db()
    restore_world(db_params(target), dump_of_world_with_visitors, confirm=False)
    with psycopg.connect(**db_params(target), autocommit=True) as owner:
        rep = scalar(owner, "SELECT id FROM company.employees WHERE title = 'Account Executive' ORDER BY id LIMIT 1")
        own_orders = scalar(owner, "SELECT count(*) FROM company.orders WHERE sales_rep_id = %s", (rep,))
        owner.execute("UPDATE company.employees SET user_id = 'u-rep' WHERE id = %s", (rep,))
    with psycopg.connect(**{**db_params(target), "user": "chattie_query", "password": os.environ["QUERY_DB_PASSWORD"]}) as query:
        with query.transaction():
            query.execute("SET LOCAL app.user_id = 'u-rep'")
            assert scalar(query, "SELECT count(*) FROM company.orders") == own_orders > 0
            assert scalar(query, "SELECT count(*) FROM company.employee_requests WHERE employee_id <> %s", (rep,)) == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            query.execute("SELECT salary FROM company.employees")
    # the restored sequences let new generated rows get ids that do not collide
    with psycopg.connect(**{**db_params(target), "user": "chattie_generator", "password": os.environ["GENERATOR_DB_PASSWORD"]}, autocommit=True) as generator:
        replace_character(generator, user_id="u-new", display_name="New", role="employee", department_id=2, today=TODAY)


def test_restore_refuses_a_populated_database_without_confirmation(world_db, dump_of_world_with_visitors, db_params):
    before = scalar(world_db, "SELECT count(*) FROM company.employees")
    with pytest.raises(RestoreRefused, match="generated characters"):
        restore_world(db_params(world_db.info.dbname), dump_of_world_with_visitors, confirm=False)
    assert scalar(world_db, "SELECT count(*) FROM company.employees") == before


def test_confirmed_restore_replaces_the_world_and_drops_visitors(world_db, dump_of_world_with_visitors, db_params):
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE origin <> 'seed'") > 0
    restore_world(db_params(world_db.info.dbname), dump_of_world_with_visitors, confirm=True)
    assert scalar(world_db, "SELECT count(*) FROM company.employees") == 33
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE origin <> 'seed'") == 0


def test_restore_never_touches_auth_or_public_tables(world_db, dump_of_world_with_visitors, db_params):
    world_db.execute("CREATE SCHEMA IF NOT EXISTS auth")
    world_db.execute('CREATE TABLE auth."user" (id text PRIMARY KEY)')
    world_db.execute("INSERT INTO auth.\"user\" VALUES ('a'), ('b')")
    world_db.execute("CREATE TABLE IF NOT EXISTS public.chat_threads (thread_id text PRIMARY KEY, user_id text)")
    world_db.execute("INSERT INTO public.chat_threads VALUES ('t1', 'a'), ('t2', 'b'), ('t3', 'b')")
    restore_world(db_params(world_db.info.dbname), dump_of_world_with_visitors, confirm=True)
    assert scalar(world_db, 'SELECT count(*) FROM auth."user"') == 2
    assert scalar(world_db, "SELECT count(*) FROM public.chat_threads") == 3
