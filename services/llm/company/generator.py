"""Deterministic company world: staff, customers, products, orders over time and per-person history.

`build_world` fills an empty `company` schema; `extend_world` appends later days (orders and work
days) without touching earlier rows. Everything is seeded: the same seed and `as_of` give the same
world. Synchronous psycopg code: it runs from the CLI and tests with the owner connection and, at
runtime, as the `chattie_generator` role (which may append for seed staff but not rewrite them).
"""

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import psycopg

from company.history import EVENT_COLUMNS, REQUEST_COLUMNS, WORK_DAY_COLUMNS, person_history, person_work_days, rng_for
from company.workcal import fictional_holidays

ORDER_HORIZON_DAYS = 540  # about 18 months of orders
GROWTH_ANCHOR = date(2025, 1, 1)
MONTHLY_GROWTH = 1.02
ORDER_BASE = 1.8  # expected orders on an average weekday of the anchor month
CANCELLED_SHARE = 0.04
WEEKDAY_WEIGHT = (1.1, 1.05, 1.0, 1.0, 0.9, 0.08, 0.04)  # Monday first; weekends are quiet
SEASON = {1: 0.85, 2: 0.9, 3: 1.0, 4: 1.0, 5: 1.0, 6: 0.95, 7: 0.9, 8: 0.85, 9: 1.05, 10: 1.25, 11: 1.4, 12: 1.3}

FIRST = ["Ava", "Liam", "Noah", "Mia", "Leo", "Zara", "Omar", "Sara", "Arash", "Nika", "Lucas", "Emma",
         "Kian", "Yara", "Elias", "Ines", "Darius", "Lena", "Hugo", "Maya", "Reza", "Chloe", "Ivan", "Anya"]
LAST = ["Karimi", "Smith", "Rossi", "Müller", "Tanaka", "Haddad", "Novak", "Silva", "Moradi", "Dubois",
        "Kowalski", "Jensen", "Ahmadi", "Lopez", "Berg", "Nasser", "Costa", "Fischer"]
COUNTRIES = ["Germany", "France", "Netherlands", "Sweden", "Italy", "United States", "Canada", "Brazil",
             "United Kingdom", "Spain", "Iran", "Turkey", "Japan"]
COMPANY_WORDS = (["Blue", "North", "Bright", "Iron", "Green", "Swift", "Silver", "Atlas", "Nova", "Crest"],
                 ["Labs", "Systems", "Logistics", "Foods", "Health", "Media", "Energy", "Retail", "Bank", "Motors"])
DEPARTMENTS = ["Executive", "Sales", "Engineering", "Marketing", "Human Resources", "Customer Support"]
PRODUCTS = {
    "Software": [("Analytics Suite", 1200), ("CRM Cloud", 900), ("Security Shield", 650), ("Data Pipeline", 1500),
                 ("Mobile SDK", 400), ("AI Assistant", 2000), ("Backup Pro", 300), ("Workflow Builder", 750)],
    "Hardware": [("Edge Gateway", 850), ("Sensor Kit", 220), ("Rack Server", 4800), ("Smart Display", 640),
                 ("Network Switch", 1300), ("Rugged Tablet", 980), ("Storage Array", 7200)],
    "Services": [("Onboarding Package", 2500), ("Premium Support", 1800), ("Custom Integration", 6000),
                 ("Cloud Migration", 9500), ("Security Audit", 4200), ("Managed Hosting", 1100)],
    "Training": [("Admin Course", 700), ("Developer Bootcamp", 2200), ("Analytics Workshop", 950),
                 ("Security Awareness", 300), ("Certification Exam", 450)],
}
SEGMENTS = {  # product category preferences by customer type
    "software": {"Software": 0.6, "Services": 0.2, "Training": 0.1, "Hardware": 0.1},
    "hardware": {"Hardware": 0.6, "Services": 0.2, "Software": 0.1, "Training": 0.1},
    "services": {"Services": 0.5, "Software": 0.2, "Training": 0.2, "Hardware": 0.1},
    "mixed": {"Software": 0.3, "Hardware": 0.3, "Services": 0.25, "Training": 0.15},
}

ORDER_INSERT = (
    "INSERT INTO company.orders (customer_id, product_id, sales_rep_id, quantity, total, status, ordered_at) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s)"
)


@dataclass
class WorldStats:
    employees: int = 0
    orders: int = 0
    requests: int = 0
    work_days: int = 0


# --- staff, customers, products ---------------------------------------------------------------


def _staff(rng, as_of: date) -> list[tuple]:
    """(id, department_id, manager_id, name, title, role, salary, hired_at): the same org shape as before."""
    names = iter(rng.sample([f"{f} {l}" for f in FIRST for l in LAST], 60))
    rows: list[tuple] = []

    def add(dept: int, manager: int | None, title: str, role: str, salary: tuple[int, int]) -> int:
        emp_id = len(rows) + 1
        hired = min(date(2016, 1, 1) + timedelta(days=rng.randrange(0, 3650)), as_of - timedelta(days=60))
        rows.append((emp_id, dept, manager, next(names), title, role, rng.randrange(*salary, 500), hired))
        return emp_id

    ceo = add(1, None, "Chief Executive Officer", "admin", (240_000, 260_000))
    for region in ("EMEA", "Americas"):
        head = add(2, ceo, f"Sales Manager, {region}", "manager", (120_000, 140_000))
        for _ in range(6):
            add(2, head, "Account Executive", "employee", (60_000, 90_000))
    for dept, title, staff, count in ((3, "Engineering Manager", "Software Engineer", 6),
                                      (4, "Marketing Manager", "Marketing Specialist", 3),
                                      (6, "Support Manager", "Support Engineer", 4)):
        head = add(dept, ceo, title, "manager", (110_000, 135_000))
        for _ in range(count):
            add(dept, head, staff, "employee", (55_000, 110_000))
    hr_head = add(5, ceo, "Head of People", "hr", (105_000, 120_000))
    add(5, hr_head, "HR Specialist", "hr", (55_000, 70_000))
    return rows


# --- orders -----------------------------------------------------------------------------------


@dataclass
class OrderContext:
    reps: list[int]
    rep_weights: list[float]
    customers: dict[int, list[int]]  # sales rep -> customer ids
    customer_weight: dict[int, float]
    customer_segment: dict[int, str]
    products: dict[str, list[tuple[int, float]]]


def _order_context(conn: psycopg.Connection, seed: int) -> OrderContext:
    """Rebuilt from the database, with weights derived from ids, so a later extension matches the build."""
    reps = [r[0] for r in conn.execute(
        "SELECT id FROM company.employees WHERE origin = 'seed' AND title = 'Account Executive' ORDER BY id")]
    customers: dict[int, list[int]] = defaultdict(list)
    for cid, rep in conn.execute("SELECT id, account_manager_id FROM company.customers ORDER BY id"):
        if rep in reps:
            customers[rep].append(cid)
    all_customers = [c for ids in customers.values() for c in ids]
    products: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for pid, category, price in conn.execute("SELECT id, category, price FROM company.products ORDER BY id"):
        products[category].append((pid, float(price)))
    return OrderContext(
        reps=reps,
        rep_weights=[rng_for(seed, "rep", r).lognormvariate(0, 0.45) for r in reps],
        customers=dict(customers),
        customer_weight={c: rng_for(seed, "cust", c).lognormvariate(0, 0.8) for c in all_customers},
        customer_segment={c: rng_for(seed, "seg", c).choice(list(SEGMENTS)) for c in all_customers},
        products=dict(products),
    )


def _poisson(rng, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def orders_for_day(seed, day: date, as_of: date, ctx: OrderContext, scale: float = 1.0) -> list[tuple]:
    """The day's orders (customer, product, rep, quantity, total, status, ordered_at).
    Seeded by the day alone, so the same day yields the same orders however the world was built."""
    rng = rng_for(seed, "orders", day)
    months = (day - GROWTH_ANCHOR).days / 30.4375
    rate = scale * ORDER_BASE * MONTHLY_GROWTH**months * SEASON[day.month] * WEEKDAY_WEIGHT[day.weekday()]
    age = (as_of - day).days
    rows = []
    for _ in range(_poisson(rng, rate)):
        rep = rng.choices(ctx.reps, ctx.rep_weights)[0]
        owned = ctx.customers[rep]
        customer = rng.choices(owned, [ctx.customer_weight[c] for c in owned])[0]
        mix = SEGMENTS[ctx.customer_segment[customer]]
        category = rng.choices(list(mix), list(mix.values()))[0]
        product, price = rng.choice(ctx.products[category])
        quantity = min(20, 1 + int(rng.expovariate(1 / 3)))
        status = ("cancelled" if rng.random() < CANCELLED_SHARE else "pending" if age < 7
                  else "shipped" if age < 21 else "delivered")
        at = datetime.combine(day, time(8), tzinfo=timezone.utc) + timedelta(minutes=rng.randrange(0, 600))
        rows.append((customer, product, rep, quantity, round(quantity * price, 2), status, at))
    return rows


# --- database helpers -------------------------------------------------------------------------


def _meta(conn: psycopg.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM company.meta WHERE key = %s", (key,)).fetchone()
    return row[0] if row else None


def ensure_holidays(cur: psycopg.Cursor, first_year: int, last_year: int) -> None:
    for year in range(first_year, last_year + 1):
        cur.executemany("INSERT INTO company.holidays (day, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        fictional_holidays(year))


def holiday_set(conn: psycopg.Connection) -> set[date]:
    return {r[0] for r in conn.execute("SELECT day FROM company.holidays")}


def _write_history(cur: psycopg.Cursor, history) -> None:
    cur.executemany(
        f"INSERT INTO company.employee_requests ({REQUEST_COLUMNS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        history.requests)
    cur.executemany(f"INSERT INTO company.work_days ({WORK_DAY_COLUMNS}) VALUES (%s,%s,%s,%s)", history.work_days)
    cur.executemany(f"INSERT INTO company.employee_events ({EVENT_COLUMNS}) VALUES (%s,%s,%s,%s,%s::jsonb)", history.events)


def clear_world(conn: psycopg.Connection) -> None:
    """Remove all company data (people, orders, history) but keep the schema and leave policy."""
    conn.execute(
        "TRUNCATE company.employee_events, company.work_days, company.employee_requests, company.orders, "
        "company.customers, company.products, company.employees, company.departments, company.holidays, "
        "company.meta RESTART IDENTITY CASCADE")


# --- build and extend -------------------------------------------------------------------------


def build_world(conn: psycopg.Connection, *, seed: int = 42, as_of: date) -> WorldStats:
    """Fill an empty company schema. Refuses to run on a world that already has people."""
    if conn.execute("SELECT count(*) FROM company.employees").fetchone()[0]:
        raise RuntimeError("the world is already built; clear it first")
    rng = rng_for(seed, "world")
    staff = _staff(rng, as_of)
    reps = [row[0] for row in staff if row[4] == "Account Executive"]
    stats = WorldStats(employees=len(staff))

    with conn.transaction(), conn.cursor() as cur:
        cur.executemany("INSERT INTO company.departments VALUES (%s, %s)", list(enumerate(DEPARTMENTS, start=1)))
        cur.executemany(
            "INSERT INTO company.employees (id, department_id, manager_id, name, title, role, salary, hired_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", staff)
        products = [(i, name, category, price) for i, (category, name, price) in enumerate(
            ((c, n, p) for c, items in PRODUCTS.items() for n, p in items), start=1)]
        cur.executemany("INSERT INTO company.products VALUES (%s, %s, %s, %s)", products)
        names = rng.sample([f"{a} {b}" for a in COMPANY_WORDS[0] for b in COMPANY_WORDS[1]], 60)
        cur.executemany("INSERT INTO company.customers VALUES (%s, %s, %s, %s)", [
            (i, name, rng.choice(COUNTRIES), reps[(i - 1) % len(reps)]) for i, name in enumerate(names, start=1)])

        ensure_holidays(cur, (as_of - timedelta(days=ORDER_HORIZON_DAYS + 5)).year, (as_of + timedelta(days=400)).year)
        cur.executemany("INSERT INTO company.meta (key, value) VALUES (%s, %s)",
                        [("as_of", as_of.isoformat()), ("seed", str(seed))])

        ctx = _order_context(conn, seed)
        for offset in range(ORDER_HORIZON_DAYS - 1, -1, -1):
            rows = orders_for_day(seed, as_of - timedelta(days=offset), as_of, ctx)
            cur.executemany(ORDER_INSERT, rows)
            stats.orders += len(rows)

        holidays = holiday_set(conn)
        for emp_id, _dept, _mgr, _name, _title, _role, _salary, hired in staff:
            history = person_history(f"{seed}:emp{emp_id}", emp_id, hired, as_of, holidays)
            _write_history(cur, history)
            stats.requests += len(history.requests)
            stats.work_days += len(history.work_days)
    return stats


def extend_world(conn: psycopg.Connection, *, to: date) -> WorldStats:
    """Append orders and work days for the days after the world's current end up to `to`.

    Earlier rows are never changed. Requests are not extended: they are generated at build time
    for a year back and 30 days ahead. Order statuses of earlier days are not advanced (that needs
    an UPDATE, which the runtime role may not do); see `advance_order_statuses`.
    """
    as_of = date.fromisoformat(_meta(conn, "as_of"))
    seed = int(_meta(conn, "seed"))
    if to <= as_of:
        return WorldStats()
    stats = WorldStats()
    first, last = as_of + timedelta(days=1), to
    with conn.transaction(), conn.cursor() as cur:
        ensure_holidays(cur, as_of.year, (to + timedelta(days=400)).year)
        holidays = holiday_set(conn)
        ctx = _order_context(conn, seed)
        day = first
        while day <= last:
            rows = orders_for_day(seed, day, to, ctx)
            cur.executemany(ORDER_INSERT, rows)
            stats.orders += len(rows)
            day += timedelta(days=1)

        approved: dict[int, list[tuple]] = defaultdict(list)
        for emp, kind, start, end in conn.execute(
            "SELECT employee_id, kind, starts_on, ends_on FROM company.employee_requests "
            "WHERE status = 'approved' AND ends_on >= %s AND starts_on <= %s", (first, last)):
            approved[emp].append((kind, "approved", start, end))
        for emp_id, hired in conn.execute("SELECT id, hired_at FROM company.employees WHERE origin = 'seed' ORDER BY id").fetchall():
            rows = person_work_days(f"{seed}:emp{emp_id}", emp_id, hired, first, last, holidays, approved[emp_id])
            cur.executemany(f"INSERT INTO company.work_days ({WORK_DAY_COLUMNS}) VALUES (%s,%s,%s,%s)", rows)
            stats.work_days += len(rows)
        cur.execute("UPDATE company.meta SET value = %s WHERE key = 'as_of'", (to.isoformat(),))
    return stats


def advance_order_statuses(conn: psycopg.Connection, as_of: date) -> int:
    """Owner-only upkeep: move pending orders older than 7 days to shipped and shipped ones older
    than 21 days to delivered. Returns the number of orders updated."""
    with conn.transaction():
        shipped = conn.execute(
            "UPDATE company.orders SET status = 'shipped' WHERE status = 'pending' "
            "AND (ordered_at AT TIME ZONE 'UTC')::date <= %s", (as_of - timedelta(days=7),)).rowcount
        delivered = conn.execute(
            "UPDATE company.orders SET status = 'delivered' WHERE status = 'shipped' "
            "AND (ordered_at AT TIME ZONE 'UTC')::date <= %s", (as_of - timedelta(days=21),)).rowcount
    return shipped + delivered


_CHECKSUM_QUERIES = [
    "SELECT id, department_id, manager_id, name, title, role, salary, hired_at, origin FROM company.employees ORDER BY id",
    "SELECT * FROM company.departments ORDER BY id",
    "SELECT * FROM company.customers ORDER BY id",
    "SELECT * FROM company.products ORDER BY id",
    "SELECT customer_id, product_id, sales_rep_id, quantity, total, status, ordered_at FROM company.orders "
    "ORDER BY ordered_at, customer_id, product_id, sales_rep_id, quantity, total",
    "SELECT * FROM company.holidays ORDER BY day",
    "SELECT employee_id, kind, starts_on, ends_on, start_time, end_time, hours, reason, status, decision_reason, "
    "request_key, created_at FROM company.employee_requests ORDER BY employee_id, starts_on, kind, request_key",
    "SELECT * FROM company.work_days ORDER BY employee_id, day",
    "SELECT employee_id, happened_at, kind, title, details FROM company.employee_events "
    "ORDER BY employee_id, happened_at, kind, title",
    "SELECT * FROM company.meta ORDER BY key",
]


def world_checksum(conn: psycopg.Connection) -> str:
    """A stable hash of the world's content (ids that depend on insertion order are left out)."""
    digest = hashlib.sha256()
    for query in _CHECKSUM_QUERIES:
        for row in conn.execute(query):
            digest.update(repr(row).encode())
        digest.update(b"|")
    return digest.hexdigest()
