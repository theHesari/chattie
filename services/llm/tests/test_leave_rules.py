"""The instant request rules, run as the chattie_app role against the real schema."""

import asyncio
from contextlib import asynccontextmanager
from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from company.leave_rules import RequestIn, RequestNotFound, cancel_request, leave_balance, submit_request
from company.workcal import fictional_holidays

TODAY = date(2026, 3, 2)  # a Monday; 2026 holidays: Jan 1, Feb 12, Mar 20, May 1, Jun 22, Aug 17, Sep 22, Nov 2, Dec 25, Dec 28


def mk(kind="day_off", start=TODAY, end=None, **extra) -> RequestIn:
    return RequestIn(kind=kind, starts_on=start, ends_on=end, request_key=uuid4(), **extra)


@pytest.fixture
def env(world_db, pick_employee, link_user):
    for year in (2025, 2026, 2027, 2028):
        for day, name in fictional_holidays(year):
            world_db.execute("INSERT INTO company.holidays VALUES (%s, %s) ON CONFLICT DO NOTHING", (day, name))
    emp = pick_employee(world_db, "title = 'Account Executive'")
    world_db.execute("UPDATE company.employees SET hired_at = '2020-01-01' WHERE id = %s", (emp,))
    for table in ("employee_requests", "work_days", "employee_events"):  # a clean slate for the rules
        world_db.execute(f"DELETE FROM company.{table} WHERE employee_id = %s", (emp,))
    link_user(world_db, "u-emp", emp)
    return SimpleNamespace(owner=world_db, emp=emp, user="u-emp")


@pytest.fixture
def engine(env, role_conn, apply_identity):
    @asynccontextmanager
    async def session():
        async with role_conn("chattie_app") as conn, conn.transaction():
            await apply_identity(conn, env.user)
            yield conn

    async def submit(req, today=TODAY):
        async with session() as conn:
            return await submit_request(conn, env.emp, req, today)

    async def cancel(request_id, today=TODAY):
        async with session() as conn:
            return await cancel_request(conn, env.emp, request_id, today)

    async def balance(year):
        async with session() as conn:
            return await leave_balance(conn, env.emp, year)

    return SimpleNamespace(submit=submit, cancel=cancel, balance=balance, env=env)


def owner_add(env, kind, start, end=None, status="approved"):
    env.owner.execute(
        "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, status, request_key) "
        "VALUES (%s, %s, %s, %s, %s, gen_random_uuid())",
        (env.emp, kind, start, end or start, status),
    )


def row_count(env):
    return env.owner.execute("SELECT count(*) FROM company.employee_requests WHERE employee_id = %s", (env.emp,)).fetchone()[0]


# --- day_off ---------------------------------------------------------------------------------


async def test_day_off_15_working_days_approved_and_16_rejected(engine):
    engine.env.owner.execute("UPDATE company.leave_policy SET annual_days = 60")  # isolate the 15-day limit
    fifteen = await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 24)))  # three full weeks
    assert fifteen.status == "approved"
    # Aug 3-24 holds a holiday (Aug 17): 16 weekdays but 15 working days, which is allowed.
    assert (await engine.submit(mk(start=date(2026, 8, 3), end=date(2026, 8, 24)))).status == "approved"
    sixteen = await engine.submit(mk(start=date(2026, 6, 1), end=date(2026, 6, 23)))  # 16 working days (Jun 22 is a holiday)
    assert sixteen.status == "rejected" and "15" in sixteen.decision_reason


async def test_balance_exactly_equal_is_approved_then_one_more_is_rejected(engine):
    assert (await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 24)))).status == "approved"  # 15
    last = await engine.submit(mk(start=date(2026, 6, 1), end=date(2026, 6, 5)))  # 5 -> exactly 20
    assert last.status == "approved" and last.balance_after == 0
    over = await engine.submit(mk(start=date(2026, 7, 6)))
    assert over.status == "rejected"
    assert "you have 0 days left, this needs 1" in over.decision_reason


async def test_short_balance_message_states_the_numbers(engine):
    engine.env.owner.execute("UPDATE company.leave_policy SET annual_days = 2")
    result = await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 8)))
    assert result.status == "rejected"
    assert result.decision_reason == "Rejected: you have 2 days left, this needs 3"


async def test_overlap_with_approved_leave_is_rejected(engine):
    assert (await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 8)))).status == "approved"
    overlap = await engine.submit(mk(start=date(2026, 4, 8), end=date(2026, 4, 10)))
    assert overlap.status == "rejected" and "overlap" in overlap.decision_reason.lower()


async def test_day_off_window_is_today_to_twelve_months(engine):
    assert (await engine.submit(mk(start=date(2026, 3, 1)))).status == "rejected"  # yesterday (a Sunday: no working day either)
    assert (await engine.submit(mk(start=date(2026, 2, 27)))).status == "rejected"  # past
    assert (await engine.submit(mk(start=date(2027, 3, 2)))).status == "approved"  # today + 365 days
    late = await engine.submit(mk(start=date(2027, 3, 3)))  # today + 366 days
    assert late.status == "rejected" and "12 months" in late.decision_reason


async def test_range_without_working_days_is_rejected(engine):
    result = await engine.submit(mk(start=date(2026, 4, 4), end=date(2026, 4, 5)))  # Saturday and Sunday
    assert result.status == "rejected" and "working day" in result.decision_reason
    holiday_only = await engine.submit(mk(start=date(2026, 3, 20)))  # Friday holiday
    assert holiday_only.status == "rejected" and "working day" in holiday_only.decision_reason


async def test_range_crossing_new_year_uses_each_years_allowance(engine):
    today = date(2026, 12, 1)
    # Use 18 of 20 days in 2026: 2 left, but 29-31 Dec are 3 working days.
    owner_add(engine.env, "day_off", "2026-03-02", "2026-03-13")  # 10
    owner_add(engine.env, "day_off", "2026-04-06", "2026-04-15")  # 8
    short = await engine.submit(mk(start=date(2026, 12, 29), end=date(2027, 1, 8)), today)
    assert short.status == "rejected"
    assert "you have 2 days left in 2026, this needs 3" in short.decision_reason
    # Use only 17: 3 left in 2026, and 2027 is untouched.
    engine.env.owner.execute("DELETE FROM company.employee_requests WHERE starts_on = '2026-04-06'")
    owner_add(engine.env, "day_off", "2026-04-06", "2026-04-14")  # 7
    ok = await engine.submit(mk(start=date(2026, 12, 29), end=date(2027, 1, 8)), today)
    assert ok.status == "approved"
    assert await engine.balance(2026) == (20, 20)
    assert await engine.balance(2027) == (20, 5)  # Jan 4-8; Jan 1 is a holiday


@pytest.mark.parametrize(
    "start,end",
    [
        (date(2026, 4, 10), date(2026, 4, 6)),  # ends before it starts
        (date(9999, 1, 1), None),  # absurdly far away
        (date(2026, 4, 6), date(2036, 4, 6)),  # a ten-year span
        (date(1900, 1, 1), None),  # long ago
    ],
)
async def test_invalid_ranges_are_rejected_not_crashed(engine, start, end):
    result = await engine.submit(mk(start=start, end=end))
    assert result.status == "rejected" and result.id is None
    assert row_count(engine.env) == 0


# --- sick_day ---------------------------------------------------------------------------------


async def test_sick_day_window_is_today_and_three_days_back(engine):
    friday = date(2026, 3, 6)
    assert (await engine.submit(mk("sick_day", start=date(2026, 3, 3)), friday)).status == "approved"  # 3 back
    result = await engine.submit(mk("sick_day", start=date(2026, 3, 2)), friday)  # 4 back
    assert result.status == "rejected" and "3 days" in result.decision_reason
    assert (await engine.submit(mk("sick_day", start=friday), friday)).status == "approved"  # today
    assert (await engine.submit(mk("sick_day", start=date(2026, 3, 9)), friday)).status == "rejected"  # the future


async def test_eleventh_sick_day_in_a_year_is_rejected(engine):
    for day in (6, 7, 8, 9, 10, 13, 14, 15, 16, 17):  # ten working days in April
        owner_add(engine.env, "sick_day", f"2026-04-{day:02d}")
    result = await engine.submit(mk("sick_day", start=TODAY))
    assert result.status == "rejected" and "10" in result.decision_reason


async def test_sick_day_never_stores_the_reason(engine):
    result = await engine.submit(mk("sick_day", start=TODAY, reason="flu"))
    assert result.status == "approved"
    stored = engine.env.owner.execute("SELECT reason FROM company.employee_requests WHERE id = %s", (result.id,)).fetchone()
    assert stored[0] is None


# --- remote_day -------------------------------------------------------------------------------


async def test_third_remote_day_in_a_week_is_rejected(engine):
    assert (await engine.submit(mk("remote_day", start=date(2026, 3, 9)))).status == "approved"
    assert (await engine.submit(mk("remote_day", start=date(2026, 3, 10)))).status == "approved"
    third = await engine.submit(mk("remote_day", start=date(2026, 3, 11)))
    assert third.status == "rejected" and "2" in third.decision_reason
    assert (await engine.submit(mk("remote_day", start=date(2026, 3, 16)))).status == "approved"  # next week


async def test_remote_day_on_approved_leave_is_rejected(engine):
    assert (await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 8)))).status == "approved"
    assert (await engine.submit(mk("remote_day", start=date(2026, 4, 7)))).status == "rejected"


# --- schedule_change --------------------------------------------------------------------------


async def test_schedule_change_must_cover_the_core_window(engine):
    covered = mk("schedule_change", start=date(2026, 3, 9), end=date(2026, 3, 13), start_time=time(8), end_time=time(16))
    assert (await engine.submit(covered)).status == "approved"
    exact = mk("schedule_change", start=date(2026, 3, 16), start_time=time(10), end_time=time(15))
    assert (await engine.submit(exact)).status == "approved"  # the window itself is enough
    late = mk("schedule_change", start=date(2026, 3, 17), start_time=time(11), end_time=time(18))
    result = await engine.submit(late)
    assert result.status == "rejected" and "10:00" in result.decision_reason


async def test_schedule_change_range_is_at_most_four_weeks(engine):
    ok = mk("schedule_change", start=date(2026, 4, 6), end=date(2026, 5, 3), start_time=time(8), end_time=time(16))
    assert (await engine.submit(ok)).status == "approved"  # 28 days
    long = mk("schedule_change", start=date(2026, 6, 1), end=date(2026, 6, 29), start_time=time(8), end_time=time(16))
    assert (await engine.submit(long)).status == "rejected"  # 29 days


async def test_schedule_change_needs_times(engine):
    assert (await engine.submit(mk("schedule_change", start=date(2026, 3, 9)))).status == "rejected"


# --- overtime ---------------------------------------------------------------------------------


async def test_overtime_limits_per_day_and_per_week(engine):
    assert (await engine.submit(mk("overtime", start=date(2026, 3, 9), hours=4))).status == "approved"
    assert (await engine.submit(mk("overtime", start=date(2026, 3, 10), hours=4.5))).status == "rejected"  # over 4 a day
    assert (await engine.submit(mk("overtime", start=date(2026, 3, 10), hours=4))).status == "approved"  # 8 so far
    over_week = await engine.submit(mk("overtime", start=date(2026, 3, 11), hours=4))  # would be 12
    assert over_week.status == "rejected" and "10" in over_week.decision_reason
    assert (await engine.submit(mk("overtime", start=date(2026, 3, 11), hours=2))).status == "approved"  # exactly 10


# --- idempotency and cancellation -------------------------------------------------------------


async def test_same_request_key_returns_the_same_result_without_a_second_row(engine):
    request = mk(start=date(2026, 4, 6))
    first = await engine.submit(request)
    second = await engine.submit(request)
    assert (first.id, first.status) == (second.id, second.status)
    assert row_count(engine.env) == 1


async def test_cancel_before_start_restores_the_balance(engine):
    approved = await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 8)))
    assert await engine.balance(2026) == (20, 3)
    cancelled = await engine.cancel(approved.id)
    assert cancelled.status == "cancelled"
    assert await engine.balance(2026) == (20, 0)
    assert (await engine.submit(mk(start=date(2026, 4, 6), end=date(2026, 4, 8)))).status == "approved"  # the days are free again


async def test_cancel_after_start_is_refused(engine):
    approved = await engine.submit(mk(start=TODAY))  # starts today
    result = await engine.cancel(approved.id)
    assert result.status == "approved" and "already started" in result.decision_reason


async def test_cancel_twice_changes_nothing(engine):
    approved = await engine.submit(mk(start=date(2026, 4, 6)))
    await engine.cancel(approved.id)
    again = await engine.cancel(approved.id)
    assert again.status == "cancelled"


async def test_cancel_of_a_missing_or_foreign_request_raises(engine):
    with pytest.raises(RequestNotFound):
        await engine.cancel(999_999)


# --- concurrency ------------------------------------------------------------------------------


async def test_two_concurrent_requests_cannot_both_spend_the_last_day(engine):
    engine.env.owner.execute("UPDATE company.leave_policy SET annual_days = 1")
    results = await asyncio.gather(
        engine.submit(mk(start=date(2026, 4, 6))),
        engine.submit(mk(start=date(2026, 4, 7))),
    )
    assert sorted(r.status for r in results) == ["approved", "rejected"]


@pytest.mark.parametrize("hours", [float("nan"), float("inf"), float("-inf"), 0, -1, 0.1, 24.5])
def test_hours_outside_a_sensible_range_never_reach_the_rules(hours):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RequestIn(kind="overtime", starts_on=TODAY, hours=hours, request_key=uuid4())


def test_a_quarter_hour_is_the_smallest_overtime():
    assert RequestIn(kind="overtime", starts_on=TODAY, hours=0.25, request_key=uuid4()).hours == 0.25
