"""Generated, persisted characters: create, replace, archive, reactivate."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import psycopg
import pytest

from company import characters
from company.characters import (
    CharacterCapExceeded,
    archive_inactive,
    clean_display_name,
    reactivate,
    replace_character,
)

TODAY = date(2026, 11, 27)
SALES, ENGINEERING = 2, 3


def make(conn, user="u-test", name="Test Person", role="employee", dept=SALES, today=TODAY):
    return replace_character(conn, user_id=user, display_name=name, role=role, department_id=dept, today=today)


def scalar(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def team_ids(conn, employee_id):
    return [r[0] for r in conn.execute(
        "SELECT id FROM company.employees WHERE manager_id = %s AND origin = 'simulated' ORDER BY name", (employee_id,))]


def row_count(conn, ids):
    queries = [
        "SELECT count(*) FROM company.employees WHERE id = ANY(%s)",
        "SELECT count(*) FROM company.employee_requests WHERE employee_id = ANY(%s)",
        "SELECT count(*) FROM company.work_days WHERE employee_id = ANY(%s)",
        "SELECT count(*) FROM company.employee_events WHERE employee_id = ANY(%s)",
        "SELECT count(*) FROM company.orders WHERE sales_rep_id = ANY(%s)",
        "SELECT count(*) FROM company.customers WHERE account_manager_id = ANY(%s)",
    ]
    return sum(scalar(conn, q, (ids,)) for q in queries)


def fingerprint(conn, user_id):
    """The character's content without database ids, so two builds can be compared."""
    me = scalar(conn, "SELECT id FROM company.employees WHERE user_id = %s", (user_id,))
    ids = [me] + team_ids(conn, me)
    def rows(select, table, col, order):
        return conn.execute(
            f"SELECT e.name, {select} FROM company.{table} t JOIN company.employees e ON e.id = t.{col} "
            f"WHERE e.id = ANY(%s) ORDER BY e.name, {order}", (ids,)).fetchall()

    return {
        "requests": rows("t.kind, t.starts_on, t.ends_on, t.status, t.decision_reason", "employee_requests", "employee_id", "t.starts_on, t.kind"),
        "work_days": rows("t.day, t.hours, t.kind", "work_days", "employee_id", "t.day"),
        "events": rows("t.kind, t.title, t.happened_at", "employee_events", "employee_id", "t.happened_at, t.title"),
        "orders": rows("t.ordered_at, t.quantity, t.total, t.status", "orders", "sales_rep_id", "t.ordered_at, t.quantity"),
        "customers": rows("t.name, t.country", "customers", "account_manager_id", "t.name"),
    }


# --- shape of a new character ---------------------------------------------------------------------


def test_employee_attaches_to_the_seeded_manager_of_the_chosen_department(world_db, generator_conn):
    character = make(generator_conn, dept=ENGINEERING)
    assert character.title == "Software Engineer" and character.role == "employee"
    assert character.department == "Engineering"
    expected = scalar(world_db, "SELECT name FROM company.employees WHERE origin = 'seed' AND department_id = %s AND role = 'manager'", (ENGINEERING,))
    assert character.manager_name == expected
    origin, user = world_db.execute("SELECT origin, user_id FROM company.employees WHERE id = %s", (character.employee_id,)).fetchone()
    assert (origin, user) == ("visitor", "u-test")


def test_manager_gets_a_small_simulated_team_of_direct_reports(world_db, generator_conn):
    character = make(generator_conn, role="manager", dept=ENGINEERING)
    team = team_ids(world_db, character.employee_id)
    assert 3 <= len(team) <= 5
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE id = ANY(%s) AND origin = 'simulated' AND user_id IS NULL", (team,)) == len(team)


@pytest.mark.parametrize("role", ["hr", "admin"])
def test_hr_and_admin_have_no_team(world_db, generator_conn, role):
    character = make(generator_conn, role=role, dept=None)
    assert team_ids(world_db, character.employee_id) == []
    assert character.role == role


def test_sales_character_gets_customers_and_orders_others_do_not(world_db, generator_conn):
    sales = make(generator_conn, user="u-sales", dept=SALES)
    assert 3 <= scalar(world_db, "SELECT count(*) FROM company.customers WHERE account_manager_id = %s", (sales.employee_id,)) <= 6
    assert scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id = %s", (sales.employee_id,)) > 0
    engineer = make(generator_conn, user="u-eng", dept=ENGINEERING)
    assert scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id = %s", (engineer.employee_id,)) == 0
    assert scalar(world_db, "SELECT count(*) FROM company.customers WHERE account_manager_id = %s", (engineer.employee_id,)) == 0


def test_row_budget_and_speed(world_db, generator_conn):
    started = time.perf_counter()
    manager = make(generator_conn, user="u-mgr", role="manager", dept=SALES)  # the biggest case: a team of sales reps
    elapsed = time.perf_counter() - started
    assert row_count(world_db, [manager.employee_id] + team_ids(world_db, manager.employee_id)) < 2000
    employee = make(generator_conn, user="u-emp", dept=SALES)
    assert row_count(world_db, [employee.employee_id]) < 600
    assert elapsed < 2.0, f"generating a sales manager took {elapsed:.2f}s (target: about a second)"


def test_history_is_a_real_year_not_empty(world_db, generator_conn):
    character = make(generator_conn)
    assert scalar(world_db, "SELECT count(*) FROM company.work_days WHERE employee_id = %s", (character.employee_id,)) > 150
    assert scalar(world_db, "SELECT count(*) FROM company.employee_requests WHERE employee_id = %s", (character.employee_id,)) >= 3
    kinds = {r[0] for r in world_db.execute("SELECT kind FROM company.employee_events WHERE employee_id = %s", (character.employee_id,))}
    assert "hired" in kinds


# --- determinism, replacement, concurrency ----------------------------------------------------------


def test_same_user_and_role_give_identical_history_after_a_rebuild(world_db, generator_conn):
    make(generator_conn, role="manager", dept=SALES)
    first = fingerprint(world_db, "u-test")
    make(generator_conn, role="manager", dept=SALES)  # replaces: new database ids, same content
    assert fingerprint(world_db, "u-test") == first


def test_different_roles_give_different_histories(world_db, generator_conn):
    make(generator_conn, role="employee")
    employee = fingerprint(world_db, "u-test")
    make(generator_conn, role="manager")
    assert fingerprint(world_db, "u-test") != employee


def seed_fingerprint(conn):
    return conn.execute(
        "SELECT md5(string_agg(e::text, '|' ORDER BY e.id)) FROM company.employees e WHERE origin = 'seed'").fetchone()[0], \
        scalar(conn, "SELECT count(*) FROM company.orders WHERE sales_rep_id <= 33"), \
        scalar(conn, "SELECT count(*) FROM company.employee_requests WHERE employee_id <= 33")


def test_role_change_replaces_the_character_and_never_touches_seed_rows(world_db, generator_conn):
    before = seed_fingerprint(world_db)
    manager = make(generator_conn, role="manager", dept=SALES)
    old_team = team_ids(world_db, manager.employee_id)
    employee = make(generator_conn, role="employee", dept=ENGINEERING)
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE user_id = 'u-test'") == 1
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE id = ANY(%s)", ([manager.employee_id] + old_team,)) == 0
    assert row_count(world_db, [manager.employee_id] + old_team) == 0
    assert employee.employee_id != manager.employee_id
    assert seed_fingerprint(world_db) == before


def test_two_simultaneous_calls_leave_exactly_one_active_character(world_db):
    def call(_):
        with psycopg.connect(
            host=os.environ.get("DB_HOST", "localhost"), port=os.environ.get("DB_PORT", "5432"), user="chattie_generator",
            password=os.environ["GENERATOR_DB_PASSWORD"], dbname=world_db.info.dbname, autocommit=True,
        ) as conn:
            return make(conn, role="manager", dept=ENGINEERING)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(call, range(2)))  # neither call may raise
    assert len(results) == 2
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE user_id = 'u-test' AND is_active") == 1
    mine = scalar(world_db, "SELECT id FROM company.employees WHERE user_id = 'u-test'")
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE origin = 'simulated'") == len(team_ids(world_db, mine))


def test_cap_counts_only_active_visitor_characters(world_db, generator_conn, monkeypatch):
    monkeypatch.setattr(characters, "MAX_ACTIVE_CHARACTERS", 3)
    for i in range(3):
        make(generator_conn, user=f"u-{i}", role="manager", dept=ENGINEERING)  # teams are simulated, not counted
    with pytest.raises(CharacterCapExceeded):
        make(generator_conn, user="u-extra")
    make(generator_conn, user="u-0", role="employee")  # replacing your own character is always allowed
    world_db.execute("UPDATE company.employees SET is_active = false, archived_at = now() WHERE user_id = 'u-1'")
    make(generator_conn, user="u-extra")  # an archived character frees its slot


# --- archive and reactivate -------------------------------------------------------------------------


def age(conn, user_id, days):
    conn.execute("UPDATE company.employees SET last_active_at = %s WHERE user_id = %s",
                 (TODAY - timedelta(days=days), user_id))


def test_archive_removes_bulky_data_keeps_requests_and_events_and_hides_the_character(world_db, generator_conn):
    manager = make(generator_conn, role="manager", dept=SALES)
    team = team_ids(world_db, manager.employee_id)
    requests = scalar(world_db, "SELECT count(*) FROM company.employee_requests WHERE employee_id = %s", (manager.employee_id,))
    events = scalar(world_db, "SELECT count(*) FROM company.employee_events WHERE employee_id = %s", (manager.employee_id,))
    age(world_db, "u-test", 31)

    assert archive_inactive(generator_conn, today=TODAY) == 1

    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE id = ANY(%s)", (team,)) == 0
    assert scalar(world_db, "SELECT count(*) FROM company.work_days WHERE employee_id = %s", (manager.employee_id,)) == 0
    assert scalar(world_db, "SELECT count(*) FROM company.orders WHERE sales_rep_id = ANY(%s)", ([manager.employee_id] + team,)) == 0
    assert scalar(world_db, "SELECT count(*) FROM company.customers WHERE account_manager_id = ANY(%s)", ([manager.employee_id] + team,)) == 0
    assert scalar(world_db, "SELECT count(*) FROM company.employee_requests WHERE employee_id = %s", (manager.employee_id,)) == requests
    assert scalar(world_db, "SELECT count(*) FROM company.employee_events WHERE employee_id = %s", (manager.employee_id,)) == events
    active, archived_at = world_db.execute("SELECT is_active, archived_at FROM company.employees WHERE id = %s", (manager.employee_id,)).fetchone()
    assert active is False and archived_at is not None


def test_archive_ignores_accounts_active_within_30_days(world_db, generator_conn):
    make(generator_conn)
    age(world_db, "u-test", 29)
    assert archive_inactive(generator_conn, today=TODAY) == 0
    assert scalar(world_db, "SELECT is_active FROM company.employees WHERE user_id = 'u-test'") is True


def test_archive_never_touches_seed_staff(world_db, generator_conn):
    world_db.execute("UPDATE company.employees SET last_active_at = %s WHERE origin = 'seed'", (TODAY - timedelta(days=400),))
    before = seed_fingerprint(world_db)  # taken after the setup change above
    assert archive_inactive(generator_conn, today=TODAY) == 0
    assert seed_fingerprint(world_db) == before
    assert scalar(world_db, "SELECT count(*) FROM company.employees WHERE origin = 'seed' AND is_active") == 33


def test_reactivate_rebuilds_identical_bulk_and_applies_the_users_requests(world_db, generator_conn):
    character = make(generator_conn, role="employee", dept=SALES)
    me = character.employee_id
    office_day = scalar(world_db, "SELECT max(day) FROM company.work_days WHERE employee_id = %s AND kind = 'office' AND day < %s",
                        (me, TODAY - timedelta(days=5)))
    before = fingerprint(world_db, "u-test")

    world_db.execute(  # a request the user filed after the character was created
        "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, status, request_key) "
        "VALUES (%s, 'day_off', %s, %s, 'approved', gen_random_uuid())", (me, office_day, office_day))
    age(world_db, "u-test", 45)
    assert archive_inactive(generator_conn, today=TODAY) == 1

    back = reactivate(generator_conn, user_id="u-test", today=TODAY)
    assert back is not None and back.employee_id == me
    assert scalar(world_db, "SELECT is_active FROM company.employees WHERE id = %s", (me,)) is True

    after = fingerprint(world_db, "u-test")
    assert after["orders"] == before["orders"] and after["customers"] == before["customers"]
    changed = [(a, b) for a, b in zip(before["work_days"], after["work_days"]) if a != b]
    assert len(changed) == 1 and changed[0][1][3] == "leave" and changed[0][1][1] == office_day
    assert any(r[1] == "day_off" and r[2] == office_day for r in after["requests"])


def test_reactivate_of_an_active_or_missing_character(world_db, generator_conn):
    assert reactivate(generator_conn, user_id="nobody", today=TODAY) is None
    character = make(generator_conn)
    assert reactivate(generator_conn, user_id="u-test", today=TODAY).employee_id == character.employee_id


# --- display names ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Ada   Lovelace ", "Ada Lovelace"),
        ("x" * 10_000, "x" * 60),
        ("Zoë 🚀 Müller", "Zoë 🚀 Müller"),
        ("سارا احمدی", "سارا احمدی"),
        ("<script>alert(1)</script>", "<script>alert(1)</script>"),  # kept as literal text; rendering escapes it
        ("a\x00b\x07c", "abc"),
        ("Ada 👨\u200d👩\u200d👧 🇩🇪 \u200fعلي", "Ada 👨\u200d👩\u200d👧 🇩🇪 \u200fعلي"),  # joiners, flags and direction marks survive
        ("Evil\u202etxt.exe", "Eviltxt.exe"),  # a right-to-left override would spoof what others read
        ("a\u200bb\ufeffc\u2060d", "abcd"),  # zero-width space, BOM and word joiner are invisible tricks
        ("x" * 59 + "\u200d👨", "x" * 59),  # the cut must not leave a dangling joiner
        ("x" * 59 + "🇩🇪", "x" * 59),  # ...nor half a flag
        ("x" * 58 + "🇩🇪", "x" * 58 + "🇩🇪"),  # a whole flag that fits is kept
    ],
)
def test_clean_display_name(raw, expected):
    assert clean_display_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\x00\x01", "\n\t"])
def test_empty_display_names_are_refused(raw):
    with pytest.raises(ValueError):
        clean_display_name(raw)


def test_unknown_department_is_refused(world_db, generator_conn):
    with pytest.raises(ValueError):
        make(generator_conn, dept=999)
