"""Believable per-person history: requests, daily work hours and a timeline.

Pure and seeded: the same inputs always give the same rows. Used for the seeded staff and for
generated characters. Rows are tuples in the column order of the matching INSERT statements.
"""

import random
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from company.workcal import working_days

REQUEST_COLUMNS = (
    "employee_id, kind, starts_on, ends_on, start_time, end_time, hours, reason, status, "
    "decision_reason, request_key, created_at, decided_at"
)
WORK_DAY_COLUMNS = "employee_id, day, hours, kind"
EVENT_COLUMNS = "employee_id, happened_at, kind, title, details"

WINDOW_BACK_DAYS = 365
WINDOW_AHEAD_DAYS = 30

DAY_OFF_REASONS = ["Family trip", "Long weekend", "Moving house", "Medical appointment", "Wedding", "Rest and recharge", "Visiting relatives"]
REMOTE_REASONS = ["Focus work", "Waiting for a delivery", "Plumber visit"]
SCHEDULE_HOURS = [(time(8), time(16)), (time(9), time(17)), (time(7), time(15)), (time(8, 30), time(16, 30))]
OVERTIME_REASONS = ["Quarter-end close", "Release support", "Customer escalation"]


@dataclass
class History:
    requests: list[tuple] = field(default_factory=list)
    work_days: list[tuple] = field(default_factory=list)
    events: list[tuple] = field(default_factory=list)


def rng_for(*parts) -> random.Random:
    """A deterministic generator from any parts (string seeding is stable across runs)."""
    return random.Random(":".join(str(p) for p in parts))


def _stamp(day: date, hour: int = 9) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=timezone.utc)


def person_requests(
    rng: random.Random,
    employee_id: int,
    hired_at: date,
    lo: date,
    hi: date,
    as_of: date,
    holidays: set[date],
    taken: set[date] | None = None,
) -> list[tuple]:
    """Requests filed for dates in [lo, hi]. `taken` holds days already on approved leave
    (and receives the new ones), so approved leave never overlaps."""
    lo = max(lo, hired_at + timedelta(days=14))
    pool = working_days(lo, hi, holidays)
    if len(pool) < 20:
        return []
    leave = taken if taken is not None else set()
    rows: list[tuple] = []

    def add(kind, start, end, status, reason, decision, *, start_time=None, end_time=None, hours=None):
        filed = start - timedelta(days=rng.randint(1, 14))
        key = uuid.UUID(int=rng.getrandbits(128), version=4)
        rows.append((employee_id, kind, start, end, start_time, end_time, hours, reason, status,
                     decision, key, _stamp(filed), _stamp(filed)))

    blocks: list[list[date]] = []
    used_per_year: Counter = Counter()
    for _ in range(rng.randint(1, 4)):
        start = rng.choice(pool)
        block = working_days(start, start + timedelta(days=14), holidays)[: rng.randint(1, 5)]
        years = Counter(d.year for d in block)
        if not block or leave.intersection(block) or any(used_per_year[y] + n > 15 for y, n in years.items()):
            continue
        status = "cancelled" if rng.random() < 0.08 else "approved"
        reason = rng.choice(DAY_OFF_REASONS)
        n = len(block)
        add("day_off", block[0], block[-1], status, reason,
            f"Approved: {n} day{'s' if n != 1 else ''} off" if status == "approved" else "Cancelled by you")
        if status == "approved":
            leave.update(block)
            used_per_year.update(years)
            blocks.append(block)
    if blocks and rng.random() < 0.5:  # a clash that was refused
        clash = rng.choice(blocks)
        add("day_off", clash[0], clash[0], "rejected", rng.choice(DAY_OFF_REASONS),
            f"Rejected: it overlaps your approved leave ({clash[0]:%d %b} to {clash[-1]:%d %b})")

    past = [d for d in pool if d <= as_of and d not in leave]
    for _ in range(rng.randint(0, 4)):
        if past:
            day = rng.choice(past)
            if day not in leave:
                leave.add(day)
                add("sick_day", day, day, "approved", None, "Approved: 1 day sick")

    per_week: Counter = Counter()
    remote_days = [d for d in pool if d not in leave]
    for _ in range(rng.randint(2, 8)):
        if remote_days:
            day = rng.choice(remote_days)
            week = day.isocalendar()[:2]
            if per_week[week] < 2 and day not in leave:
                per_week[week] += 1
                add("remote_day", day, day, "approved", rng.choice(REMOTE_REASONS), "Approved: 1 day remote")

    for _ in range(rng.randint(0, 2)):
        start = rng.choice(pool)
        end = start + timedelta(days=rng.randint(4, 13))
        start_time, end_time = rng.choice(SCHEDULE_HOURS)
        n = len(working_days(start, end, holidays))
        add("schedule_change", start, end, "approved", "Adjusted hours", f"Approved: working hours {start_time:%H:%M}-{end_time:%H:%M} for {n} days",
            start_time=start_time, end_time=end_time)

    for _ in range(rng.randint(0, 3)):
        day = rng.choice(pool)
        hours = rng.choice([1, 1.5, 2, 2.5, 3])
        add("overtime", day, day, "approved", rng.choice(OVERTIME_REASONS), f"Approved: {hours:g} hours of overtime on 1 day", hours=hours)
    return rows


def person_work_days(
    seed_key: str,
    employee_id: int,
    hired_at: date,
    lo: date,
    hi: date,
    holidays: set[date],
    requests: list[tuple],
) -> list[tuple]:
    """One row per day from `lo` to `hi` (weekends skipped). `requests` are
    (kind, status, starts_on, ends_on) tuples; only approved ones shape the days."""
    leave, sick, remote = set(), set(), set()
    for kind, status, start, end in requests:
        if status != "approved":
            continue
        target = {"day_off": leave, "sick_day": sick, "remote_day": remote}.get(kind)
        if target is not None:
            target.update(working_days(start, end, holidays))
    rows = []
    day = max(lo, hired_at)
    while day <= hi:
        if day.weekday() < 5:
            if day in holidays:
                rows.append((employee_id, day, 0, "holiday"))
            elif day in leave:
                rows.append((employee_id, day, 0, "leave"))
            elif day in sick:
                rows.append((employee_id, day, 0, "sick"))
            else:
                r = rng_for(seed_key, "wd", day)
                kind = "remote" if day in remote or r.random() < 0.2 else "office"
                rows.append((employee_id, day, r.choice([8, 8, 8, 7.5, 8.5]), kind))
        day += timedelta(days=1)
    return rows


def person_events(rng: random.Random, employee_id: int, hired_at: date, as_of: date, requests: list[tuple]) -> list[tuple]:
    """Timeline entries. Titles and details never carry salary amounts."""
    import json

    events = [(employee_id, _stamp(hired_at), "hired", "Joined the company", json.dumps({}))]
    for year in range(hired_at.year + 1, as_of.year + 1):
        review = date(year, 2, rng.randint(10, 25))
        if review <= as_of:
            events.append((employee_id, _stamp(review, 14), "review", "Annual review", json.dumps({})))
    if as_of - hired_at > timedelta(days=730) and rng.random() < 0.3:
        promoted = hired_at + timedelta(days=rng.randint(365, (as_of - hired_at).days))
        events.append((employee_id, _stamp(promoted, 10), "promoted", "Promoted", json.dumps({"note": "Moved up a level"})))
    for row in requests:
        kind, start, end, status = row[1], row[2], row[3], row[8]
        if kind == "day_off":
            events.append((employee_id, row[11], "request_decided", f"Day off {status}",
                           json.dumps({"from": start.isoformat(), "to": end.isoformat()})))
    return events


def person_history(
    seed_key: str,
    employee_id: int,
    hired_at: date,
    as_of: date,
    holidays: set[date],
    taken: set[date] | None = None,
    back_days: int = WINDOW_BACK_DAYS,
) -> History:
    """A year (or `back_days`) of history up to `as_of`, plus requests for the next 30 days.

    `seed_key` must identify the person and nothing that changes between rebuilds (never a
    database id): the same key always gives the same history. `employee_id` only labels the rows."""
    rng = rng_for(seed_key, "person")
    lo = as_of - timedelta(days=back_days - 1)
    requests = person_requests(rng, employee_id, hired_at, lo, as_of + timedelta(days=WINDOW_AHEAD_DAYS), as_of, holidays, taken)
    shape = [(r[1], r[8], r[2], r[3]) for r in requests]
    return History(
        requests=requests,
        work_days=person_work_days(seed_key, employee_id, hired_at, lo, as_of, holidays, shape),
        events=person_events(rng, employee_id, hired_at, as_of, requests),
    )
