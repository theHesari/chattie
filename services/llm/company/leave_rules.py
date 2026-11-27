"""Instant request rules: submit or cancel a request and get the decision in the same call.

Runs in the caller's transaction as the `chattie_app` role with `app.user_id` set, so row-level
security still applies. The employee row is locked first, which serialises concurrent requests
from one person (two requests cannot spend the same balance). The decision comes only from the
rules below; neither the model nor any workflow takes part in it.
"""

from collections import Counter
from datetime import date, time, timedelta
from typing import Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel, Field

from company.workcal import prorated_allowance, working_days

Kind = Literal["day_off", "sick_day", "remote_day", "schedule_change", "overtime"]

MAX_SPAN_DAYS = 366
WINDOW_AHEAD_DAYS = 365  # "within the next 12 months"
MAX_CONSECUTIVE_WORKING_DAYS = 15
SICK_DAYS_PER_YEAR = 10
SICK_LOOKBACK_DAYS = 3
REMOTE_DAYS_PER_WEEK = 2
SCHEDULE_MAX_DAYS = 28
CORE_START, CORE_END = time(10, 0), time(15, 0)
OVERTIME_HOURS_PER_DAY = 4.0
OVERTIME_HOURS_PER_WEEK = 10.0
LOOKBACK_DAYS = {"day_off": 0, "sick_day": SICK_LOOKBACK_DAYS, "remote_day": 0, "schedule_change": 0, "overtime": 3}


class RequestNotFound(Exception):
    """No such request for this employee."""


class NoActiveCharacter(Exception):
    """The caller has no active character (for example it was replaced while this call was running)."""


class RequestIn(BaseModel):
    kind: Kind
    starts_on: date
    ends_on: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    hours: float | None = Field(default=None, ge=0.25, le=24, allow_inf_nan=False)
    reason: str | None = Field(default=None, max_length=500)
    request_key: UUID


class RequestResult(BaseModel):
    id: int | None  # None when the request was malformed and nothing was stored
    status: Literal["approved", "rejected", "cancelled"]
    decision_reason: str
    balance_after: int | None = None  # day-off days left in the request's year


def _plural(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def _reject(message: str) -> tuple[str, str]:
    return "rejected", f"Rejected: {message}"


def _approve(message: str) -> tuple[str, str]:
    return "approved", f"Approved: {message}"


# --- pure validation --------------------------------------------------------------------------


def _validate(req: RequestIn, ends: date, today: date) -> str | None:
    """Reasons a request cannot even be stored (nothing is written for these)."""
    if ends < req.starts_on:
        return "the end date is before the start date"
    if (ends - req.starts_on).days + 1 > MAX_SPAN_DAYS:
        return f"a request can span at most {MAX_SPAN_DAYS} days"
    offset = (req.starts_on - today).days
    if req.kind == "sick_day":
        if offset < -SICK_LOOKBACK_DAYS or ends > today:
            return f"sick days can only be recorded for today or the last {SICK_LOOKBACK_DAYS} days"
    elif offset < -LOOKBACK_DAYS[req.kind]:
        return "it can't start in the past" if LOOKBACK_DAYS[req.kind] == 0 else (
            f"it can't be recorded more than {LOOKBACK_DAYS[req.kind]} days back"
        )
    if offset > WINDOW_AHEAD_DAYS:
        return "it must start within the next 12 months"
    if req.kind == "schedule_change" and (req.start_time is None or req.end_time is None or req.end_time <= req.start_time):
        return "a schedule change needs a start time and a later end time"
    if req.kind == "overtime" and (req.hours is None or req.hours <= 0):
        return "overtime needs a number of hours"
    return None


# --- database helpers -------------------------------------------------------------------------


async def _lock_employee(conn: psycopg.AsyncConnection, employee_id: int) -> date:
    row = await (await conn.execute("SELECT hired_at FROM company.employees WHERE id = %s FOR UPDATE", (employee_id,))).fetchone()
    if row is None:
        raise NoActiveCharacter("no active character")
    return row[0]


async def _holidays(conn: psycopg.AsyncConnection, lo: date, hi: date) -> set[date]:
    rows = await (await conn.execute("SELECT day FROM company.holidays WHERE day BETWEEN %s AND %s", (lo, hi))).fetchall()
    return {r[0] for r in rows}


async def _approved(conn, employee_id: int, kinds: list[str], lo: date, hi: date) -> list[tuple]:
    """Approved requests of these kinds that touch [lo, hi]: (starts_on, ends_on, hours)."""
    cursor = await conn.execute(
        "SELECT starts_on, ends_on, hours FROM company.employee_requests "
        "WHERE employee_id = %s AND status = 'approved' AND kind = ANY(%s) AND starts_on <= %s AND ends_on >= %s "
        "ORDER BY starts_on",
        (employee_id, kinds, hi, lo),
    )
    return await cursor.fetchall()


async def _used_in_year(conn, employee_id: int, kind: str, year: int) -> int:
    first, last = date(year, 1, 1), date(year, 12, 31)
    holidays = await _holidays(conn, first, last)
    rows = await _approved(conn, employee_id, [kind], first, last)
    return sum(len(working_days(max(s, first), min(e, last), holidays)) for s, e, _ in rows)


async def _annual_days(conn) -> int:
    return (await (await conn.execute("SELECT annual_days FROM company.leave_policy")).fetchone())[0]


async def _balance(conn, employee_id: int, hired_at: date, year: int) -> tuple[int, int]:
    allowance = prorated_allowance(hired_at, year, await _annual_days(conn))
    return allowance, await _used_in_year(conn, employee_id, "day_off", year)


async def leave_balance(conn: psycopg.AsyncConnection, employee_id: int, year: int) -> tuple[int, int]:
    """(allowance, used) of day-off working days for a calendar year."""
    row = await (await conn.execute("SELECT hired_at FROM company.employees WHERE id = %s", (employee_id,))).fetchone()
    if row is None:
        raise NoActiveCharacter("no active character")
    return await _balance(conn, employee_id, row[0], year)


def _week(day: date) -> tuple[int, int]:
    iso = day.isocalendar()
    return iso[0], iso[1]


# --- the rules --------------------------------------------------------------------------------


async def _decide(conn, employee_id: int, req: RequestIn, ends: date, today: date, hired_at: date) -> tuple[str, str]:
    holidays = await _holidays(conn, req.starts_on - timedelta(days=7), ends + timedelta(days=7))
    days = working_days(req.starts_on, ends, holidays)
    if not days:
        return _reject("that range has no working days (weekends and holidays don't count)")

    if req.kind in ("day_off", "sick_day", "remote_day"):
        clash = await _approved(conn, employee_id, ["day_off", "sick_day"], req.starts_on, ends)
        if clash:
            return _reject(f"it overlaps your approved leave ({clash[0][0]:%d %b} to {clash[0][1]:%d %b})")

    if req.kind == "day_off":
        if len(days) > MAX_CONSECUTIVE_WORKING_DAYS:
            return _reject(f"a single request can cover at most {MAX_CONSECUTIVE_WORKING_DAYS} working days (this one covers {len(days)})")
        spans_years = len({d.year for d in days}) > 1
        for year, needed in sorted(Counter(d.year for d in days).items()):
            allowance, used = await _balance(conn, employee_id, hired_at, year)
            if needed > allowance - used:
                where = f" in {year}" if spans_years else ""
                return _reject(f"you have {_plural(allowance - used)} left{where}, this needs {needed}")
        return _approve(f"{_plural(len(days))} off")

    if req.kind == "sick_day":
        for year, needed in sorted(Counter(d.year for d in days).items()):
            used = await _used_in_year(conn, employee_id, "sick_day", year)
            if used + needed > SICK_DAYS_PER_YEAR:
                return _reject(f"{used} of {SICK_DAYS_PER_YEAR} sick days are already used in {year}, this needs {needed}")
        return _approve(f"{_plural(len(days))} sick")

    if req.kind == "remote_day":
        existing: Counter = Counter()
        for s, e, _ in await _approved(conn, employee_id, ["remote_day"], days[0] - timedelta(days=7), days[-1] + timedelta(days=7)):
            existing.update(_week(d) for d in working_days(s, e, holidays))
        for week, new in Counter(_week(d) for d in days).items():
            if existing[week] + new > REMOTE_DAYS_PER_WEEK:
                return _reject(f"remote work is limited to {REMOTE_DAYS_PER_WEEK} days a week")
        return _approve(f"{_plural(len(days))} remote")

    if req.kind == "schedule_change":
        if (ends - req.starts_on).days + 1 > SCHEDULE_MAX_DAYS:
            return _reject("a schedule change can last at most 4 weeks")
        if req.start_time > CORE_START or req.end_time < CORE_END:
            return _reject("your working hours must include the core window 10:00-15:00")
        return _approve(f"working hours {req.start_time:%H:%M}-{req.end_time:%H:%M} for {_plural(len(days))}")

    # overtime: hours are per working day in the range
    if req.hours > OVERTIME_HOURS_PER_DAY:
        return _reject(f"overtime is limited to {OVERTIME_HOURS_PER_DAY:g} hours a day")
    per_week: Counter = Counter()
    for s, e, hours in await _approved(conn, employee_id, ["overtime"], days[0] - timedelta(days=7), days[-1] + timedelta(days=7)):
        for d in working_days(s, e, holidays):
            per_week[_week(d)] += float(hours or 0)
    for d in days:
        per_week[_week(d)] += req.hours
    worst = max(per_week[_week(d)] for d in days)
    if worst > OVERTIME_HOURS_PER_WEEK:
        return _reject(f"overtime is limited to {OVERTIME_HOURS_PER_WEEK:g} hours a week (that week would reach {worst:g})")
    return _approve(f"{req.hours:g} hours of overtime on {_plural(len(days))}")


# --- public API -------------------------------------------------------------------------------


async def _result(conn, employee_id: int, hired_at: date, request_id: int, status: str, reason: str, kind: str, starts_on: date):
    balance = None
    if kind == "day_off":
        allowance, used = await _balance(conn, employee_id, hired_at, starts_on.year)
        balance = allowance - used
    return RequestResult(id=request_id, status=status, decision_reason=reason, balance_after=balance)


async def submit_request(conn: psycopg.AsyncConnection, employee_id: int, req: RequestIn, today: date) -> RequestResult:
    ends = req.ends_on or req.starts_on
    problem = _validate(req, ends, today)
    if problem:
        return RequestResult(id=None, status="rejected", decision_reason=f"Rejected: {problem}")

    hired_at = await _lock_employee(conn, employee_id)

    seen = await (
        await conn.execute(
            "SELECT id, status, decision_reason, kind, starts_on FROM company.employee_requests "
            "WHERE employee_id = %s AND request_key = %s",
            (employee_id, req.request_key),
        )
    ).fetchone()
    if seen:  # the same request sent again (a double click): answer with the original decision
        return await _result(conn, employee_id, hired_at, seen[0], seen[1], seen[2], seen[3], seen[4])

    status, reason = await _decide(conn, employee_id, req, ends, today, hired_at)
    stored_reason = None if req.kind == "sick_day" else ((req.reason or "").strip() or None)
    request_id = (
        await (
            await conn.execute(
                "INSERT INTO company.employee_requests (employee_id, kind, starts_on, ends_on, start_time, end_time, "
                "hours, reason, status, decision_reason, request_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (employee_id, req.kind, req.starts_on, ends, req.start_time, req.end_time, req.hours,
                 stored_reason, status, reason, req.request_key),
            )
        ).fetchone()
    )[0]
    return await _result(conn, employee_id, hired_at, request_id, status, reason, req.kind, req.starts_on)


async def cancel_request(conn: psycopg.AsyncConnection, employee_id: int, request_id: int, today: date) -> RequestResult:
    hired_at = await _lock_employee(conn, employee_id)
    row = await (
        await conn.execute(
            "SELECT status, kind, starts_on FROM company.employee_requests WHERE id = %s AND employee_id = %s",
            (request_id, employee_id),
        )
    ).fetchone()
    if row is None:
        raise RequestNotFound(str(request_id))
    status, kind, starts_on = row
    if status == "cancelled":
        return await _result(conn, employee_id, hired_at, request_id, "cancelled", "Already cancelled", kind, starts_on)
    if status == "rejected":
        return await _result(conn, employee_id, hired_at, request_id, "rejected", "Only approved requests can be cancelled", kind, starts_on)
    if starts_on <= today:
        return await _result(conn, employee_id, hired_at, request_id, "approved", "Can't cancel: it has already started", kind, starts_on)
    await conn.execute(
        "UPDATE company.employee_requests SET status = 'cancelled', decision_reason = 'Cancelled by you', decided_at = now() "
        "WHERE id = %s",
        (request_id,),
    )
    return await _result(conn, employee_id, hired_at, request_id, "cancelled", "Cancelled by you", kind, starts_on)
