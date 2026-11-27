"""Row-level security, grants and constraints of the people tables (migration 0002)."""

import psycopg
import pytest


# --- owner-side helpers -------------------------------------------------------------------


def add_request(conn, employee_id, *, kind="day_off", start="2026-03-02", end=None, status="approved"):
    conn.execute(
        "INSERT INTO company.employee_requests "
        "(employee_id, kind, starts_on, ends_on, status, request_key) "
        "VALUES (%s, %s, %s, %s, %s, gen_random_uuid())",
        (employee_id, kind, start, end or start, status),
    )


def add_person_rows(conn, employee_id):
    add_request(conn, employee_id)
    conn.execute("INSERT INTO company.work_days (employee_id, day, hours, kind) VALUES (%s, '2026-03-02', 8, 'office')", (employee_id,))
    conn.execute(
        "INSERT INTO company.employee_events (employee_id, happened_at, kind, title) "
        "VALUES (%s, now(), 'hired', 'Joined the company')",
        (employee_id,),
    )


PERSON_TABLES = ("employee_requests", "work_days", "employee_events")


async def owners_seen(role_conn, apply_identity, user_id, table, role="chattie_query"):
    """Distinct employee ids whose rows of `table` this caller can read."""
    async with role_conn(role) as conn, conn.transaction():
        await apply_identity(conn, user_id)
        rows = await (await conn.execute(f"SELECT DISTINCT employee_id FROM company.{table}")).fetchall()
        return {row[0] for row in rows}


@pytest.fixture
def people(world_db, pick_employee):
    """Three people with rows in every person table: a manager, one of their reports, and an
    unrelated employee from another team. Also returns hr and admin ids."""
    manager = pick_employee(world_db, "title LIKE 'Sales Manager%'")
    report = pick_employee(world_db, f"manager_id = {manager}")
    stranger = pick_employee(world_db, f"role = 'employee' AND manager_id <> {manager}")
    ids = {
        "manager": manager,
        "report": report,
        "stranger": stranger,
        "hr": pick_employee(world_db, "role = 'hr'"),
        "admin": pick_employee(world_db, "role = 'admin'"),
    }
    for employee_id in (manager, report, stranger):
        for table in PERSON_TABLES:  # start from a clean slate: the generated history would collide
            world_db.execute(f"DELETE FROM company.{table} WHERE employee_id = %s", (employee_id,))
        add_person_rows(world_db, employee_id)
    return ids


# --- visibility ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", PERSON_TABLES)
async def test_employee_sees_only_own_rows(people, world_db, link_user, role_conn, apply_identity, table):
    link_user(world_db, "u-report", people["report"])
    assert await owners_seen(role_conn, apply_identity, "u-report", table) == {people["report"]}


@pytest.mark.parametrize("table", PERSON_TABLES)
async def test_manager_sees_own_and_direct_reports_but_not_strangers(
    people, world_db, link_user, role_conn, apply_identity, table
):
    link_user(world_db, "u-mgr", people["manager"])
    team = {r[0] for r in world_db.execute("SELECT id FROM company.employees WHERE manager_id = %s", (people["manager"],))}
    seen = await owners_seen(role_conn, apply_identity, "u-mgr", table)
    assert seen == {people["manager"]} | team
    assert people["stranger"] not in seen


@pytest.mark.parametrize("who", ["hr", "admin"])
@pytest.mark.parametrize("table", PERSON_TABLES)
async def test_hr_and_admin_see_everyone(people, world_db, link_user, role_conn, apply_identity, who, table):
    link_user(world_db, f"u-{who}", people[who])
    seen = await owners_seen(role_conn, apply_identity, f"u-{who}", table)
    everyone = {r[0] for r in world_db.execute(f"SELECT DISTINCT employee_id FROM company.{table}")}
    assert seen == everyone and {people["manager"], people["report"], people["stranger"]} <= seen


@pytest.mark.parametrize("table", PERSON_TABLES)
async def test_unlinked_user_sees_nothing(people, role_conn, apply_identity, table):
    assert await owners_seen(role_conn, apply_identity, "u-nobody", table) == set()


async def test_inactive_employee_is_hidden_from_everyone_else(
    people, world_db, link_user, role_conn, apply_identity
):
    link_user(world_db, "u-mgr", people["manager"])
    link_user(world_db, "u-admin", people["admin"])
    world_db.execute("UPDATE company.employees SET is_active = false WHERE id = %s", (people["report"],))
    for user in ("u-mgr", "u-admin"):
        assert people["report"] not in await owners_seen(role_conn, apply_identity, user, "employee_requests")
        async with role_conn("chattie_query") as conn, conn.transaction():
            await apply_identity(conn, user)
            directory = {r[0] for r in await (await conn.execute("SELECT id FROM company.employees")).fetchall()}
        assert people["report"] not in directory


async def test_archived_user_sees_nothing_until_reactivated(people, world_db, link_user, role_conn, apply_identity):
    link_user(world_db, "u-report", people["report"])
    world_db.execute("UPDATE company.employees SET is_active = false WHERE id = %s", (people["report"],))
    assert await owners_seen(role_conn, apply_identity, "u-report", "employee_requests") == set()
    world_db.execute("UPDATE company.employees SET is_active = true WHERE id = %s", (people["report"],))
    assert await owners_seen(role_conn, apply_identity, "u-report", "employee_requests") == {people["report"]}


# --- privileges of the three roles ----------------------------------------------------------

INSERT_REQUEST = (
    "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, status, request_key) "
    "VALUES (%s, 'day_off', '2026-06-01', '2026-06-01', 'approved', gen_random_uuid())"
)


async def test_query_role_cannot_insert_requests(people, role_conn):
    async with role_conn("chattie_query") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute(INSERT_REQUEST, (people["report"],))


async def test_app_role_can_insert_only_for_own_employee(people, world_db, link_user, role_conn, apply_identity):
    link_user(world_db, "u-report", people["report"])
    async with role_conn("chattie_app") as conn:
        async with conn.transaction():
            await apply_identity(conn, "u-report")
            await conn.execute(INSERT_REQUEST, (people["report"],))  # own: allowed
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await apply_identity(conn, "u-report")
                await conn.execute(INSERT_REQUEST, (people["stranger"],))  # someone else's: refused


async def test_app_role_cannot_delete_or_touch_salaries(people, world_db, link_user, role_conn, apply_identity):
    link_user(world_db, "u-report", people["report"])
    async with role_conn("chattie_app") as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await apply_identity(conn, "u-report")
                await conn.execute("DELETE FROM company.employee_requests")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            await conn.execute("SELECT salary FROM company.employees")


async def test_generator_cannot_modify_or_delete_seed_employees(people, role_conn):
    async with role_conn("chattie_generator") as conn:
        for statement in (
            "UPDATE company.employees SET title = 'Hacked' WHERE id = %s",
            "DELETE FROM company.employees WHERE id = %s",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(statement, (people["report"],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO company.employees (department_id, name, title, role, salary, hired_at, origin) "
                    "VALUES (1, 'Fake Seed', 'x', 'employee', 1, '2020-01-01', 'seed')"
                )


async def test_generator_can_write_visitor_rows(people, role_conn):
    async with role_conn("chattie_generator") as conn, conn.transaction():
        new_id = (
            await (
                await conn.execute(
                    "INSERT INTO company.employees (department_id, name, title, role, salary, hired_at, origin) "
                    "VALUES (1, 'New Visitor', 'Account Executive', 'employee', 50000, '2025-01-01', 'visitor') "
                    "RETURNING id"
                )
            ).fetchone()
        )[0]
        assert new_id >= 1000  # visitor ids come from the sequence, clear of the seeded ids
        await conn.execute(INSERT_REQUEST, (new_id,))
        await conn.execute("UPDATE company.employees SET title = 'Senior AE' WHERE id = %s", (new_id,))
        await conn.execute("DELETE FROM company.employees WHERE id = %s", (new_id,))


async def test_generator_can_append_but_not_rewrite_seed_history(people, world_db, role_conn):
    rep = world_db.execute("SELECT sales_rep_id, customer_id, product_id FROM company.orders LIMIT 1").fetchone()
    async with role_conn("chattie_generator") as conn:
        async with conn.transaction():  # appending a new row for a seeded rep is allowed
            await conn.execute(
                "INSERT INTO company.orders (customer_id, product_id, sales_rep_id, quantity, total, status, ordered_at) "
                "VALUES (%s, %s, %s, 1, 10, 'pending', now())",
                (rep[1], rep[2], rep[0]),
            )
        for statement in (
            "UPDATE company.orders SET total = 0 WHERE sales_rep_id = %s",
            "DELETE FROM company.orders WHERE sales_rep_id = %s",
            "DELETE FROM company.employee_requests WHERE employee_id = %s",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                async with conn.transaction():
                    await conn.execute(statement, (people["report"] if "requests" in statement else rep[0],))


# --- constraints ----------------------------------------------------------------------------


def test_overlapping_approved_leave_is_rejected_by_the_database(people, world_db):
    emp = people["report"]
    add_request(world_db, emp, start="2026-05-04", end="2026-05-06")
    with pytest.raises(psycopg.errors.ExclusionViolation):
        add_request(world_db, emp, start="2026-05-06", end="2026-05-08")
    with pytest.raises(psycopg.errors.ExclusionViolation):
        add_request(world_db, emp, kind="sick_day", start="2026-05-05")
    add_request(world_db, emp, start="2026-05-07", end="2026-05-08")  # adjacent is fine
    add_request(world_db, emp, start="2026-05-04", status="rejected")  # only approved leave counts
    add_request(world_db, emp, kind="remote_day", start="2026-05-05")  # other kinds may share a day


def test_duplicate_request_key_is_rejected(people, world_db):
    insert = (
        "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, status, request_key) "
        "VALUES (%s, 'remote_day', %s, %s, 'approved', '11111111-1111-1111-1111-111111111111')"
    )
    emp = people["report"]
    world_db.execute(insert, (emp, "2026-07-06", "2026-07-06"))
    with pytest.raises(psycopg.errors.UniqueViolation):
        world_db.execute(insert, (emp, "2026-07-13", "2026-07-13"))


def test_sick_day_never_stores_a_reason(people, world_db):
    with pytest.raises(psycopg.errors.CheckViolation):
        world_db.execute(
            "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, reason, status, request_key) "
            "VALUES (%s, 'sick_day', '2026-08-03', '2026-08-03', 'flu', 'approved', gen_random_uuid())",
            (people["report"],),
        )


def test_events_cannot_carry_salary_data(people, world_db):
    with pytest.raises(psycopg.errors.CheckViolation):
        world_db.execute(
            "INSERT INTO company.employee_events (employee_id, happened_at, kind, title, details) "
            "VALUES (%s, now(), 'review', 'Salary review', '{\"new_salary\": 90000}')",
            (people["report"],),
        )
    world_db.execute(  # the event itself is fine; only amounts are refused
        "INSERT INTO company.employee_events (employee_id, happened_at, kind, title) "
        "VALUES (%s, now(), 'review', 'Salary review')",
        (people["report"],),
    )


def test_leave_balance_view_counts_working_days_only(people, world_db, link_user):
    emp = people["report"]
    link_user(world_db, "u-report", emp)
    world_db.execute("UPDATE company.employees SET hired_at = '2020-01-01' WHERE id = %s", (emp,))
    world_db.execute("DELETE FROM company.employee_requests WHERE employee_id = %s", (emp,))  # fixture's own row
    world_db.execute("INSERT INTO company.holidays VALUES (make_date(extract(year FROM current_date)::int, 3, 4), 'Test Day')")
    year = world_db.execute("SELECT extract(year FROM current_date)::int").fetchone()[0]
    # Mon 2 March to Fri 6 March, with Wed 4 March a holiday: 4 working days.
    add_request(world_db, emp, start=f"{year}-03-02", end=f"{year}-03-06")
    with world_db.transaction():
        world_db.execute("SET LOCAL app.user_id = 'u-report'")
        world_db.execute("SET LOCAL ROLE chattie_query")
        row = world_db.execute("SELECT allowance, used, remaining FROM company.my_leave_balance").fetchone()
    assert row == (20, 4, 16)


# --- performance: the chat SQL tool times out after 5 seconds ------------------------------------


@pytest.mark.parametrize("role_title", ["employee", "manager", "hr", "admin"])
async def test_full_reads_stay_well_inside_the_tool_timeout(
    world_db, link_user, pick_employee, role_conn, apply_identity, role_title
):
    """Policies are evaluated once per query, not per row: reading everything a role may see is fast."""
    import time

    link_user(world_db, "u-perf", pick_employee(world_db, f"role = '{role_title}'"))
    tables = ("work_days", "employee_requests", "employee_events", "orders", "customers", "employees")
    async with role_conn("chattie_query") as conn, conn.transaction():
        await apply_identity(conn, "u-perf")
        for table in tables:
            runs = []
            for _ in range(3):  # the best of three: a busy machine slows a run, a slow policy slows every run
                started = time.perf_counter()
                await (await conn.execute(f"SELECT count(*) FROM company.{table}")).fetchone()
                runs.append(time.perf_counter() - started)
            assert min(runs) < 2.0, f"{role_title} reading {table} took {min(runs):.1f}s at best"
