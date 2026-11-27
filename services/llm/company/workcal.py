"""Working days, the company's invented holidays, and leave allowance. Pure functions, no database."""

from datetime import date, timedelta

# Invented, fixed-date holidays: the fictional company follows no real country's calendar.
_HOLIDAYS = [
    (1, 1, "New Year Break"),
    (2, 12, "Founders' Day"),
    (3, 20, "Spring Equinox Day"),
    (5, 1, "Workers' Day"),
    (6, 21, "Midsummer Day"),
    (8, 15, "Harvest Day"),
    (9, 22, "Autumn Equinox Day"),
    (10, 31, "Lantern Day"),
    (12, 25, "Winter Holiday"),
    (12, 26, "Winter Holiday (second day)"),
]


def fictional_holidays(year: int) -> list[tuple[date, str]]:
    """The year's holidays, in date order. A holiday that lands on a weekend (or on another
    holiday) moves to the next free weekday, so none falls on a weekend and none overlap."""
    taken: set[date] = set()
    result = []
    for month, day, name in _HOLIDAYS:
        moved = date(year, month, day)
        while moved.weekday() >= 5 or moved in taken:
            moved += timedelta(days=1)
        taken.add(moved)
        result.append((moved, name))
    return sorted(result)


def is_working_day(day: date, holidays: set[date]) -> bool:
    return day.weekday() < 5 and day not in holidays


def working_days(start: date, end: date, holidays: set[date]) -> list[date]:
    """Working days from `start` to `end`, inclusive. Empty if `end` is before `start`."""
    if end < start:
        return []
    span = (end - start).days + 1  # counting avoids date overflow near date.max
    return [d for d in (start + timedelta(days=i) for i in range(span)) if is_working_day(d, holidays)]


def prorated_allowance(hire: date, year: int, annual: int = 20) -> int:
    """Leave days for a calendar year: none before the hire year, the full amount after it,
    and in the hire year the share of months remaining (hire month included), rounded half up."""
    if year < hire.year:
        return 0
    if year > hire.year:
        return annual
    months_left = 12 - hire.month + 1
    return int(annual * months_left / 12 + 0.5)
