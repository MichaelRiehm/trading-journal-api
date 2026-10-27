from datetime import UTC, date, datetime

import pytest

from trading_journal.domain import iso_week


@pytest.mark.parametrize(
    ("value", "monday"),
    [
        ("2026-W42", date(2026, 10, 12)),
        ("2026-W01", date(2025, 12, 29)),  # ISO week 1 can start in the previous year
        ("2026-W53", date(2026, 12, 28)),  # 2026 starts on a Thursday, so it has 53 weeks
    ],
)
def test_parse_valid_weeks(value: str, monday: date) -> None:
    assert iso_week.parse_iso_week(value) == monday


@pytest.mark.parametrize(
    "value",
    [
        "2025-W53",  # 2025 has 52 weeks
        "2026-W00",
        "2026-W54",
        "2026-42",
        "2026-W4",
        "2026-W042",
        "26-W42",
        "2026-w42",
        " 2026-W42",
        "2026-W42 ",
        "",
    ],
)
def test_parse_rejects_invalid_weeks(value: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - each case has its own message
        iso_week.parse_iso_week(value)


@pytest.mark.parametrize(
    ("day", "label"),
    [
        (date(2026, 10, 12), "2026-W42"),
        (date(2026, 10, 18), "2026-W42"),  # Sunday is the last day of the ISO week
        (date(2025, 12, 29), "2026-W01"),
        (date(2027, 1, 1), "2026-W53"),
    ],
)
def test_week_label(day: date, label: str) -> None:
    assert iso_week.week_label(day) == label


def test_week_start_and_bounds() -> None:
    assert iso_week.week_start(date(2026, 10, 18)) == date(2026, 10, 12)
    assert iso_week.week_bounds(date(2026, 10, 12)) == (
        datetime(2026, 10, 12, tzinfo=UTC),
        datetime(2026, 10, 19, tzinfo=UTC),
    )
