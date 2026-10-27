"""ISO 8601 weeks ("2026-W42"): Monday 00:00 UTC up to the next Monday (ADR 0012)."""

import re
from datetime import UTC, date, datetime, time, timedelta

_WEEK = re.compile(r"(\d{4})-W(\d{2})")


def parse_iso_week(value: str) -> date:
    """The Monday of an ISO week. Raises ValueError for a malformed or nonexistent week."""
    match = _WEEK.fullmatch(value)
    if match is None:
        raise ValueError("week must look like 2026-W42")
    year, week = int(match[1]), int(match[2])
    try:
        # Rejects W00, W54, and W53 in a year that has only 52 weeks.
        return date.fromisocalendar(year, week, 1)
    except ValueError:
        raise ValueError(f"{value} is not a week of {year}") from None


def week_start(day: date) -> date:
    """The Monday of the ISO week that contains `day`."""
    return day - timedelta(days=day.weekday())


def week_label(day: date) -> str:
    """'2026-W42' for any day of that week. The ISO year can differ from the calendar year."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_bounds(monday: date) -> tuple[datetime, datetime]:
    """[start, end) of the week in UTC: the end is the next Monday, excluded."""
    start = datetime.combine(monday, time(), tzinfo=UTC)
    return start, start + timedelta(weeks=1)
