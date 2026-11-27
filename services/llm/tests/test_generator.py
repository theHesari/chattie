"""The deterministic world generator: staff, orders over time, history, and catch-up."""

import os
from datetime import date, timedelta

import psycopg
import pytest

from company.generator import build_world, clear_world, extend_world, world_checksum
from db.migrate import apply_migrations

AS_OF = date(2026, 11, 27)  # a Friday


@pytest.fixture
def empty_company(owner_conn):
    """Migrated schema with no world in it."""
    owner_conn.execute("DROP SCHEMA IF EXISTS company CASCADE")
    owner_conn.execute("DROP TABLE IF EXISTS public.schema_migrations")
    apply_migrations(owner_conn)
    return owner_conn


@pytest.fixture
def world(world_db):
    """The session's generated world (seed 42, AS_OF) in a private clone; AS_OF matches conftest."""
    return world_db


def scalar(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def test_world_has_the_expected_shape(world):
    assert scalar(world, "select count(*) from company.employees") == 33
    assert scalar(world, "select count(*) from company.customers") == 60
    assert 800 <= scalar(world, "select count(*) from company.orders") <= 1300
    assert scalar(world, "select count(*) from company.employees where origin = 'seed'") == 33
    assert scalar(world, "select value from company.meta where key = 'as_of'") == AS_OF.isoformat()


def test_same_seed_and_date_give_identical_checksum(empty_company):
    build_world(empty_company, seed=42, as_of=AS_OF)
    first = world_checksum(empty_company)
    clear_world(empty_company)
    build_world(empty_company, seed=42, as_of=AS_OF)
    assert world_checksum(empty_company) == first


def test_different_seed_differs(empty_company):
    build_world(empty_company, seed=42, as_of=AS_OF)
    first = world_checksum(empty_company)
    clear_world(empty_company)
    build_world(empty_company, seed=7, as_of=AS_OF)
    assert world_checksum(empty_company) != first


def test_building_twice_without_clearing_is_refused(world):  # the clone already holds a world
    with pytest.raises(Exception, match="already"):
        build_world(world, seed=42, as_of=AS_OF)


def test_every_department_has_a_manager(world):
    missing = world.execute(
        "select d.name from company.departments d where not exists "
        "(select 1 from company.employees e where e.department_id = d.id and e.role in ('manager', 'hr', 'admin'))"
    ).fetchall()
    assert missing == []


def test_every_sales_rep_has_customers_and_orders(world):
    quiet = world.execute(
        "select e.id from company.employees e where e.title = 'Account Executive' "
        "and not exists (select 1 from company.orders o where o.sales_rep_id = e.id)"
    ).fetchall()
    assert quiet == []


def test_weekend_orders_are_under_15_percent(world):
    weekend = scalar(world, "select count(*) from company.orders where extract(isodow from ordered_at at time zone 'UTC') >= 6")
    assert weekend / scalar(world, "select count(*) from company.orders") < 0.15


def test_q4_has_a_higher_daily_order_rate_than_other_months(world):
    rows = world.execute(
        "select extract(month from ordered_at at time zone 'UTC')::int in (10, 11, 12) as q4, count(*), "
        "count(distinct (ordered_at at time zone 'UTC')::date) from company.orders group by 1"
    ).fetchall()
    rate = {q4: n / days for q4, n, days in rows}
    assert rate[True] > rate[False]


def test_about_4_percent_cancelled(world):
    share = scalar(world, "select count(*) filter (where status = 'cancelled')::float / count(*) from company.orders")
    assert 0.02 <= share <= 0.07


def test_order_status_depends_on_age(world):
    ages = {
        status: world.execute(
            "select min(%s::date - (ordered_at at time zone 'UTC')::date), max(%s::date - (ordered_at at time zone 'UTC')::date) "
            "from company.orders where status = %s", (AS_OF, AS_OF, status)).fetchone()
        for status in ("pending", "shipped", "delivered")
    }
    assert ages["pending"][1] < 7
    assert 7 <= ages["shipped"][0] and ages["shipped"][1] < 21
    assert ages["delivered"][0] >= 21


def test_orders_span_about_18_months(world):
    first, last = world.execute(
        "select min((ordered_at at time zone 'UTC')::date), max((ordered_at at time zone 'UTC')::date) from company.orders"
    ).fetchone()
    assert AS_OF - timedelta(days=540) <= first <= AS_OF - timedelta(days=500)
    assert last >= AS_OF - timedelta(days=4)
    assert last <= AS_OF


def test_work_days_never_on_weekends_or_holidays_except_kind_holiday(world):
    weekends = scalar(world, "select count(*) from company.work_days where extract(isodow from day) >= 6")
    on_holiday = scalar(
        world, "select count(*) from company.work_days w join company.holidays h on h.day = w.day where w.kind <> 'holiday'")
    assert weekends == 0 and on_holiday == 0


def test_approved_requests_shape_the_work_days(world):
    mismatches = scalar(
        world,
        "select count(*) from company.employee_requests r join company.work_days w "
        "on w.employee_id = r.employee_id and w.day between r.starts_on and r.ends_on "
        "where r.status = 'approved' and r.kind = 'day_off' and w.kind not in ('leave', 'holiday')",
    )
    assert mismatches == 0


def test_requests_exist_for_the_next_30_days(world):
    upcoming = scalar(
        world, "select count(*) from company.employee_requests where status = 'approved' and starts_on > %s", (AS_OF,))
    assert upcoming > 0
    assert scalar(world, "select max(starts_on) from company.employee_requests") <= AS_OF + timedelta(days=30)


def test_no_salary_amounts_in_events(world):
    assert scalar(world, "select count(*) from company.employee_events where details::text ~* 'salary'") == 0
    assert scalar(world, "select count(*) from company.employee_events where title ~* '[$€£]|salary [0-9]'") == 0


def test_extend_world_only_adds_rows_after_as_of(world):
    def history():
        return world.execute(
            "select ordered_at, customer_id, product_id, sales_rep_id, quantity, total from company.orders "
            "where (ordered_at at time zone 'UTC')::date <= %s order by id", (AS_OF,)).fetchall()

    orders_before = history()
    days_before = scalar(world, "select count(*) from company.work_days")
    stats = extend_world(world, to=AS_OF + timedelta(days=14))
    assert stats.orders > 0 and stats.work_days > 0
    assert history() == orders_before  # nothing earlier changed
    assert scalar(world, "select min((ordered_at at time zone 'UTC')::date) from company.orders where id > (select max(id) - %s from company.orders)", (stats.orders - 1,)) > AS_OF
    assert scalar(world, "select count(*) from company.work_days") == days_before + stats.work_days
    assert scalar(world, "select value from company.meta where key = 'as_of'") == (AS_OF + timedelta(days=14)).isoformat()


def test_extend_is_idempotent(world):
    target = AS_OF + timedelta(days=10)
    extend_world(world, to=target)
    checksum = world_checksum(world)
    again = extend_world(world, to=target)
    assert (again.orders, again.work_days, again.requests) == (0, 0, 0)
    assert world_checksum(world) == checksum


def test_extend_runs_as_the_generator_role(world):
    """Catch-up runs at runtime as chattie_generator: appending for seed staff must be allowed."""
    with psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"), port=os.environ.get("DB_PORT", "5432"),
        user="chattie_generator", password=os.environ["GENERATOR_DB_PASSWORD"], dbname=world.info.dbname, autocommit=True,
    ) as conn:
        stats = extend_world(conn, to=AS_OF + timedelta(days=7))
    assert stats.orders > 0
