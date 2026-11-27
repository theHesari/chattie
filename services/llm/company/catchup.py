"""Keeping things current as real time passes: the shared world and each persisted character.

Both are idempotent and safe to call on every request: they do nothing when already current. The
world catch-up runs at most once at a time (a database lock), so concurrent requests do not
duplicate the work. Runs as `chattie_generator`.
"""

from datetime import date, timedelta

import psycopg

from company.characters import ORDER_SCALE, SALES, sales_context, seed_key, team_ids
from company.generator import ORDER_HORIZON_DAYS, ORDER_INSERT, ensure_holidays, extend_world, holiday_set, orders_for_day
from company.history import WORK_DAY_COLUMNS, person_work_days


def catch_up_world(conn: psycopg.Connection, today: date) -> bool:
    """Extend the shared world (orders, work days of seed staff) up to `today`. True if work was done;
    False if it was already current or another process is doing it right now."""
    with conn.transaction():
        if not conn.execute("SELECT pg_try_advisory_xact_lock(hashtext('company-world-catchup'))").fetchone()[0]:
            return False
        row = conn.execute("SELECT value FROM company.meta WHERE key = 'as_of'").fetchone()
        if row is None:  # no generated world yet (for example data left over from before the generator)
            return False
        if date.fromisoformat(row[0]) >= today:
            return False
        extend_world(conn, to=today)
        return True


def _extend_person(conn, cur, person_id: int, slot: str, hired: date, today: date, holidays: set[date], sells: bool) -> int:
    added = 0
    last = conn.execute("SELECT max(day) FROM company.work_days WHERE employee_id = %s", (person_id,)).fetchone()[0]
    start = last + timedelta(days=1) if last else max(hired, today - timedelta(days=364))
    if start <= today:
        approved = conn.execute(
            "SELECT kind, status, starts_on, ends_on FROM company.employee_requests "
            "WHERE employee_id = %s AND status = 'approved' AND ends_on >= %s AND starts_on <= %s", (person_id, start, today)).fetchall()
        rows = person_work_days(slot, person_id, hired, start, today, holidays, approved)
        cur.executemany(f"INSERT INTO company.work_days ({WORK_DAY_COLUMNS}) VALUES (%s,%s,%s,%s)", rows)
        added += len(rows)
    if sells:
        customers = [r[0] for r in conn.execute(
            "SELECT id FROM company.customers WHERE account_manager_id = %s ORDER BY id", (person_id,))]
        if customers:
            last_order = conn.execute(
                "SELECT max((ordered_at AT TIME ZONE 'UTC')::date) FROM company.orders WHERE sales_rep_id = %s", (person_id,)).fetchone()[0]
            day = last_order + timedelta(days=1) if last_order else max(hired, today - timedelta(days=ORDER_HORIZON_DAYS - 1))
            ctx = sales_context(conn, slot, person_id, customers)
            while day <= today:
                cur.executemany(ORDER_INSERT, orders_for_day(slot, day, today, ctx, scale=ORDER_SCALE))
                day += timedelta(days=1)
    return added


def catch_up_character(conn: psycopg.Connection, employee_id: int, today: date) -> int:
    """Add the work days (and, for sales, orders) a character and their simulated team have missed
    since they were last brought up to date. Returns the number of work days added; 0 for an unknown,
    seeded or archived employee."""
    row = conn.execute(
        "SELECT user_id, role, department_id, hired_at, origin, is_active FROM company.employees WHERE id = %s", (employee_id,)).fetchone()
    if row is None or row[4] != "visitor" or not row[5]:
        return 0
    user_id, role, dept, hired = row[0], row[1], row[2], row[3]
    key = seed_key(user_id, role)
    with conn.transaction(), conn.cursor() as cur:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"character:{user_id}",))
        ensure_holidays(cur, today.year, today.year + 1)
        holidays = holiday_set(conn)
        added = _extend_person(conn, cur, employee_id, f"{key}:self", hired, today, holidays, sells=(dept == SALES and role == "employee"))
        for i, teammate in enumerate(team_ids(conn, employee_id)):
            team_hired = conn.execute("SELECT hired_at FROM company.employees WHERE id = %s", (teammate,)).fetchone()[0]
            added += _extend_person(conn, cur, teammate, f"{key}:team{i}", team_hired, today, holidays, sells=(dept == SALES))
    return added
