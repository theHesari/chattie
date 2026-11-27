from datetime import date

from company.workcal import fictional_holidays, is_working_day, prorated_allowance, working_days


def holiday_set(*years: int) -> set[date]:
    return {day for year in years for day, _ in fictional_holidays(year)}


def test_weekends_and_holidays_are_not_working_days():
    holidays = holiday_set(2026)
    assert is_working_day(date(2026, 3, 2), holidays)  # a plain Monday
    assert not is_working_day(date(2026, 3, 7), holidays)  # Saturday
    assert not is_working_day(date(2026, 3, 8), holidays)  # Sunday
    assert not is_working_day(date(2026, 1, 1), holidays)  # New Year Break (Thursday)


def test_range_crossing_new_year_splits_by_year():
    # 25 Dec 2026 (Fri) is a holiday; 26 Dec (Sat) moves to Mon 28 Dec; 1 Jan 2027 (Fri) is a holiday.
    days = working_days(date(2026, 12, 28), date(2027, 1, 8), holiday_set(2026, 2027))
    assert [d for d in days if d.year == 2026] == [date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31)]
    assert [d for d in days if d.year == 2027] == [date(2027, 1, d) for d in (4, 5, 6, 7, 8)]


def test_zero_working_days_returns_empty():
    assert working_days(date(2026, 3, 7), date(2026, 3, 8), set()) == []  # Saturday and Sunday
    assert working_days(date(2026, 3, 10), date(2026, 3, 9), set()) == []  # end before start


def test_range_is_inclusive():
    assert working_days(date(2026, 3, 2), date(2026, 3, 6), set()) == [date(2026, 3, d) for d in range(2, 7)]


def test_allowance_full_year_is_20():
    assert prorated_allowance(date(2020, 5, 5), 2026) == 20
    assert prorated_allowance(date(2026, 1, 15), 2026) == 20  # January hire still has the full year


def test_allowance_hired_in_july_is_10():
    assert prorated_allowance(date(2026, 7, 20), 2026) == 10  # July to December: 6 of 12 months


def test_allowance_leap_day_hire():
    assert prorated_allowance(date(2024, 2, 29), 2024) == 18  # 11 months remaining: 20 * 11 / 12 = 18.3


def test_allowance_before_hire_year_is_zero():
    assert prorated_allowance(date(2026, 7, 1), 2025) == 0


def test_holidays_never_fall_on_weekends():
    for year in (2024, 2025, 2026, 2027, 2028):
        holidays = fictional_holidays(year)
        assert 8 <= len(holidays) <= 12
        assert len({day for day, _ in holidays}) == len(holidays)  # no two on the same day
        assert all(day.weekday() < 5 and day.year == year for day, _ in holidays)
