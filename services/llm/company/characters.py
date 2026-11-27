"""Generated, persisted characters: one per account, with their own history.

A character is a new employee row (origin 'visitor') attached to a seeded manager, with a year of
believable history. A manager also gets a small simulated team; a sales character gets customers
and orders. Everything is seeded from the account id and role, never from database ids, so the same
account and role always get the same content. Runs as `chattie_generator` (bypasses row-level
security; a trigger stops it from changing seed staff), in one transaction per call.
"""

import hashlib
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

import psycopg
from pydantic import BaseModel

from company.generator import (
    COMPANY_WORDS, COUNTRIES, FIRST, LAST, ORDER_HORIZON_DAYS, ORDER_INSERT, SEGMENTS,
    OrderContext, holiday_set, orders_for_day,
)
from company.history import EVENT_COLUMNS, REQUEST_COLUMNS, WORK_DAY_COLUMNS, person_history, person_work_days, rng_for

Role = Literal["employee", "manager", "hr", "admin"]

MAX_ACTIVE_CHARACTERS = 500
NAME_MAX_CHARS = 60
TEAM_SIZE = (3, 5)
CUSTOMERS_PER_REP = (3, 6)
ORDER_SCALE = 1 / 20  # a generated rep sells a twentieth of the company's order rate
SELF_BACK_DAYS, TEAM_BACK_DAYS = 365, 180
SALES, HR, EXECUTIVE = 2, 5, 1

STAFF_TITLE = {2: "Account Executive", 3: "Software Engineer", 4: "Marketing Specialist", 6: "Support Engineer"}
MANAGER_TITLE = {2: "Sales Manager, Nordics", 3: "Engineering Manager", 4: "Marketing Manager", 6: "Support Manager"}
SALARY = {"employee": (55_000, 90_000), "manager": (110_000, 135_000), "hr": (90_000, 120_000), "admin": (200_000, 260_000)}


class CharacterCapExceeded(Exception):
    """Too many active characters; nothing was changed."""


class CharacterOut(BaseModel):
    employee_id: int
    name: str
    title: str
    role: str
    department: str
    manager_name: str | None


# Invisible format characters that real names and emoji need: the two joiners (family emoji, Persian and
# Indic scripts) and the left/right marks. The others (overrides, zero-width spaces, BOM) are dropped: they
# can make a name read differently from what it is.
_KEPT_FORMAT_CHARS = {"\u200c", "\u200d", "\u200e", "\u200f"}


def _is_regional_indicator(ch: str) -> bool:
    return "\U0001f1e6" <= ch <= "\U0001f1ff"


def clean_display_name(raw: str) -> str:
    """Plain text, whitespace collapsed, control and invisible-trick characters dropped, at most 60
    characters, never cut in the middle of an emoji sequence or a flag. HTML stays literal text (the
    page escapes it when rendering)."""
    kept = "".join(ch for ch in raw if ch in _KEPT_FORMAT_CHARS or unicodedata.category(ch)[0] != "C" or ch in "\t\n ")
    cleaned = " ".join(kept.split())[:NAME_MAX_CHARS]
    while cleaned and cleaned[-1] in "\u200c\u200d":  # a joiner with nothing after it
        cleaned = cleaned[:-1]
    trailing = len(cleaned) - len(cleaned.rstrip("".join(chr(c) for c in range(0x1F1E6, 0x1F200))))
    if trailing % 2 == 1:  # half a flag: a flag is two regional indicators
        cleaned = cleaned[:-1]
    cleaned = cleaned.rstrip()
    if not cleaned:
        raise ValueError("a display name is required")
    return cleaned


def _stamp(day: date) -> datetime:
    return datetime.combine(day, time(12), tzinfo=timezone.utc)


def _character_out(conn: psycopg.Connection, employee_id: int) -> CharacterOut | None:
    """The character as shown to the user, or None if the employee no longer exists (it may have been
    replaced by a concurrent call)."""
    row = conn.execute(
        "SELECT e.id, e.name, e.title, e.role, d.name, m.name FROM company.employees e "
        "JOIN company.departments d ON d.id = e.department_id "
        "LEFT JOIN company.employees m ON m.id = e.manager_id WHERE e.id = %s", (employee_id,)).fetchone()
    if row is None:
        return None
    return CharacterOut(employee_id=row[0], name=row[1], title=row[2], role=row[3], department=row[4], manager_name=row[5])


def team_ids(conn: psycopg.Connection, employee_id: int) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM company.employees WHERE manager_id = %s AND origin = 'simulated' ORDER BY id", (employee_id,))]


def _delete_generated_commerce(conn: psycopg.Connection, ids: list[int]) -> None:
    conn.execute(
        "DELETE FROM company.orders WHERE sales_rep_id = ANY(%s) "
        "OR customer_id IN (SELECT id FROM company.customers WHERE account_manager_id = ANY(%s))", (ids, ids))
    conn.execute("DELETE FROM company.customers WHERE account_manager_id = ANY(%s)", (ids,))


def _delete_character(conn: psycopg.Connection, user_id: str) -> None:
    row = conn.execute("SELECT id, origin FROM company.employees WHERE user_id = %s", (user_id,)).fetchone()
    if row is None:
        return
    if row[1] == "seed":
        raise ValueError("this account is linked to a seeded employee; unlink it first")
    ids = [row[0], *team_ids(conn, row[0])]
    _delete_generated_commerce(conn, ids)
    conn.execute("DELETE FROM company.employees WHERE id = ANY(%s)", (ids,))  # requests, days, events cascade


# --- building ---------------------------------------------------------------------------------


def seed_key(user_id: str, role: str) -> str:
    return hashlib.sha256(f"{user_id}:{role}".encode()).hexdigest()[:16]


def _insert_employee(conn, *, dept, manager, name, title, role, salary, hired, user_id, origin, today) -> int:
    return conn.execute(
        "INSERT INTO company.employees (department_id, manager_id, name, title, role, salary, hired_at, user_id, "
        "origin, is_active, last_active_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s) RETURNING id",
        (dept, manager, name, title, role, salary, hired, user_id, origin, _stamp(today))).fetchone()[0]


def _write_history(cur: psycopg.Cursor, history, *, work_days_only: bool = False) -> None:
    if not work_days_only:
        cur.executemany(f"INSERT INTO company.employee_requests ({REQUEST_COLUMNS}) VALUES "
                        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", history.requests)
        cur.executemany(f"INSERT INTO company.employee_events ({EVENT_COLUMNS}) VALUES (%s,%s,%s,%s,%s::jsonb)", history.events)
    cur.executemany(f"INSERT INTO company.work_days ({WORK_DAY_COLUMNS}) VALUES (%s,%s,%s,%s)", history.work_days)


def sales_context(conn: psycopg.Connection, slot_key: str, rep_id: int, customer_ids: list[int]) -> OrderContext:
    """Order context of one generated rep. Weights come from the customer's position (ids ordered), not
    its id, so the same rep yields the same orders however many times the world was rebuilt."""
    products: dict[str, list[tuple[int, float]]] = {}
    for pid, category, price in conn.execute("SELECT id, category, price FROM company.products ORDER BY id"):
        products.setdefault(category, []).append((pid, float(price)))
    return OrderContext(
        reps=[rep_id], rep_weights=[1.0], customers={rep_id: customer_ids},
        customer_weight={cid: rng_for(slot_key, "cw", i).lognormvariate(0, 0.8) for i, cid in enumerate(customer_ids)},
        customer_segment={cid: rng_for(slot_key, "seg", i).choice(list(SEGMENTS)) for i, cid in enumerate(customer_ids)},
        products=products)


def _build_sales(conn, cur, slot_key: str, rep_id: int, hired: date, today: date) -> None:
    """A few customers for this rep and their orders since they joined (at most 18 months)."""
    rng = rng_for(slot_key, "customers")
    names = rng.sample([f"{a} {b}" for a in COMPANY_WORDS[0] for b in COMPANY_WORDS[1]], rng.randint(*CUSTOMERS_PER_REP))
    ids = [conn.execute("INSERT INTO company.customers (name, country, account_manager_id) VALUES (%s, %s, %s) RETURNING id",
                        (name, rng.choice(COUNTRIES), rep_id)).fetchone()[0] for name in names]
    ctx = sales_context(conn, slot_key, rep_id, ids)
    day = max(hired, today - timedelta(days=ORDER_HORIZON_DAYS - 1))
    while day <= today:
        cur.executemany(ORDER_INSERT, orders_for_day(slot_key, day, today, ctx, scale=ORDER_SCALE))
        day += timedelta(days=1)


def _build_team(conn, cur, key: str, me: int, dept: int, today: date, holidays: set[date]) -> list[tuple[int, date]]:
    """3-5 simulated reports with their own history (and sales, in the sales department)."""
    rng = rng_for(key, "team")
    count = rng.randint(*TEAM_SIZE)
    names = rng.sample([f"{f} {l}" for f in FIRST for l in LAST], count)
    team = []
    for i, name in enumerate(names):
        hired = today - timedelta(days=rng.randint(200, 3 * 365))
        pid = _insert_employee(conn, dept=dept, manager=me, name=name, title=STAFF_TITLE[dept], role="employee",
                               salary=rng.randrange(*SALARY["employee"], 500), hired=hired, user_id=None,
                               origin="simulated", today=today)
        slot = f"{key}:team{i}"
        _write_history(cur, person_history(slot, pid, hired, today, holidays, back_days=TEAM_BACK_DAYS))
        if dept == SALES:
            _build_sales(conn, cur, slot, pid, hired, today)
        team.append((pid, hired))
    return team


def _validate(role: str, department_id: int | None) -> tuple[int, str, str | None]:
    """(department id, title, manager lookup) for the role; raises ValueError for bad input."""
    if role in ("employee", "manager"):
        dept = SALES if department_id is None else department_id
        if dept not in STAFF_TITLE:
            raise ValueError(f"department {department_id} cannot host an employee or manager")
        return dept, (STAFF_TITLE if role == "employee" else MANAGER_TITLE)[dept], None
    if role == "hr":
        return HR, "HR Business Partner", None
    if role == "admin":
        return EXECUTIVE, "Operations Director", None
    raise ValueError(f"unknown role {role!r}")


def _manager_for(conn, rng, role: str, dept: int) -> int | None:
    if role == "employee":
        options = [r[0] for r in conn.execute(
            "SELECT id FROM company.employees WHERE origin = 'seed' AND department_id = %s AND role = 'manager' ORDER BY id", (dept,))]
    elif role == "manager":
        options = [r[0] for r in conn.execute("SELECT id FROM company.employees WHERE origin = 'seed' AND role = 'admin' ORDER BY id")]
    elif role == "hr":
        options = [r[0] for r in conn.execute(
            "SELECT id FROM company.employees WHERE origin = 'seed' AND title = 'Head of People' ORDER BY id")]
    else:
        return None
    return rng.choice(options) if options else None


def replace_character(
    conn: psycopg.Connection, *, user_id: str, display_name: str, role: Role, department_id: int | None, today: date,
) -> CharacterOut:
    """Give the account a fresh character, deleting any previous one (and its generated data)."""
    name = clean_display_name(display_name)
    dept, title, _ = _validate(role, department_id)
    key = seed_key(user_id, role)
    with conn.transaction(), conn.cursor() as cur:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"character:{user_id}",))
        _delete_character(conn, user_id)
        active = conn.execute("SELECT count(*) FROM company.employees WHERE origin = 'visitor' AND is_active").fetchone()[0]
        if active >= MAX_ACTIVE_CHARACTERS:
            raise CharacterCapExceeded(f"the platform is at its limit of {MAX_ACTIVE_CHARACTERS} active characters")

        rng = rng_for(key, "self")
        hired = today - timedelta(days=rng.randint(365, 4 * 365))
        holidays = holiday_set(conn)
        me = _insert_employee(conn, dept=dept, manager=_manager_for(conn, rng, role, dept), name=name, title=title, role=role,
                              salary=rng.randrange(*SALARY[role], 500), hired=hired, user_id=user_id, origin="visitor", today=today)
        _write_history(cur, person_history(f"{key}:self", me, hired, today, holidays, back_days=SELF_BACK_DAYS))
        if role == "employee" and dept == SALES:
            _build_sales(conn, cur, f"{key}:self", me, hired, today)
        if role == "manager":
            _build_team(conn, cur, key, me, dept, today, holidays)
        return _character_out(conn, me)


def archive_inactive(conn: psycopg.Connection, *, today: date, days: int = 30) -> int:
    """Archive visitor characters inactive for more than `days`: the bulky generated data (work days,
    simulated team, customers, orders) is removed; the employee row, the requests and the events stay.
    Returns how many were archived. Seed staff are never touched."""
    cutoff = today - timedelta(days=days)
    stale = [r[0] for r in conn.execute(
        "SELECT id FROM company.employees WHERE origin = 'visitor' AND is_active "
        "AND coalesce(last_active_at, created_at) < %s ORDER BY id", (cutoff,))]
    for me in stale:
        with conn.transaction():
            team = team_ids(conn, me)
            conn.execute("DELETE FROM company.work_days WHERE employee_id = %s", (me,))
            _delete_generated_commerce(conn, [me, *team])
            if team:
                conn.execute("DELETE FROM company.employees WHERE id = ANY(%s)", (team,))
            conn.execute("UPDATE company.employees SET is_active = false, archived_at = now() WHERE id = %s", (me,))
    return len(stale)


def reactivate(conn: psycopg.Connection, *, user_id: str, today: date) -> CharacterOut | None:
    """Bring an archived character back: same row, the user's own requests intact, bulky data rebuilt
    from the same seed (their approved requests shape the work days). No character: None.

    Safe to call from several requests at once (a dashboard fires many on load): the state is re-read
    under the per-account lock, so only the first caller rebuilds and the rest see an active character."""
    row = conn.execute("SELECT id, is_active, origin FROM company.employees WHERE user_id = %s", (user_id,)).fetchone()
    if row is None or row[2] != "visitor":
        return None
    if row[1]:
        return _character_out(conn, row[0])
    with conn.transaction(), conn.cursor() as cur:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"character:{user_id}",))
        current = conn.execute(
            "SELECT id, role, department_id, hired_at, is_active FROM company.employees WHERE user_id = %s AND origin = 'visitor'",
            (user_id,)).fetchone()
        if current is None:  # replaced or removed while we waited for the lock
            return None
        me, role, dept, hired, active = current
        if active:  # another call reactivated it while we waited
            return _character_out(conn, me)
        key = seed_key(user_id, role)
        holidays = holiday_set(conn)
        conn.execute("UPDATE company.employees SET is_active = true, archived_at = NULL, last_active_at = %s WHERE id = %s",
                     (_stamp(today), me))
        kept = [(k, s, a, b) for k, s, a, b in conn.execute(
            "SELECT kind, status, starts_on, ends_on FROM company.employee_requests WHERE employee_id = %s", (me,))]
        lo = today - timedelta(days=SELF_BACK_DAYS - 1)
        cur.executemany(f"INSERT INTO company.work_days ({WORK_DAY_COLUMNS}) VALUES (%s,%s,%s,%s)",
                        person_work_days(f"{key}:self", me, hired, lo, today, holidays, kept))
        if role == "employee" and dept == SALES:
            _build_sales(conn, cur, f"{key}:self", me, hired, today)
        if role == "manager":
            _build_team(conn, cur, key, me, dept, today, holidays)
        return _character_out(conn, me)
