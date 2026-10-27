"""Analytics endpoints against trades with hand-computed numbers (ADR 0011).

Every trade opens at 100 x 10 with a stop at 95, so 1R is $50.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import create_closed_trade, create_strategy, create_trade, registered_headers

ENTRY = "2026-10-01T14:30:00Z"  # a Thursday, ISO week 2026-W40


@pytest.fixture
def book(api_client: TestClient) -> dict[str, Any]:
    """A win, a loss and a breakeven, plus trades analytics must ignore."""
    _, headers = registered_headers(api_client)
    strategy = create_strategy(api_client, headers)
    win = create_closed_trade(
        api_client,
        headers,
        exit_price="110",  # +100 = +2R
        exit_at="2026-10-05T20:00:00Z",
        strategy_id=strategy["id"],
    )
    loss = create_closed_trade(
        api_client,
        headers,
        exit_price="95",  # -50 = -1R
        exit_at="2026-10-06T20:00:00Z",
        followed_plan=False,
        strategy_id=strategy["id"],
        symbol="MSFT",
    )
    breakeven = create_closed_trade(
        api_client,
        headers,
        exit_price="100",  # 0
        exit_at="2026-10-07T20:00:00Z",
        side="short",
        planned_stop="105.00",
        planned_target="85.00",
    )
    for status in ("planned", "open", "cancelled"):
        create_trade(api_client, headers, status=status)
    return {
        "headers": headers,
        "strategy": strategy,
        "win": win,
        "loss": loss,
        "breakeven": breakeven,
    }


def get(client: TestClient, path: str, headers: dict[str, str], **params: Any) -> Any:
    response = client.get(path, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- summary ---------------------------------------------------------------------


def test_summary_counts_closed_trades_only(api_client: TestClient, book: dict[str, Any]) -> None:
    summary = get(api_client, "/analytics/summary", book["headers"])
    assert summary == {
        "trade_count": 3,
        "wins": 1,
        "losses": 1,
        "breakevens": 1,
        "win_rate": "0.3333",
        "expectancy": "16.66666667",
        "expectancy_r": "0.3333",
        "average_win": "100.00000000",
        "average_loss": "-50.00000000",
        "average_win_r": "2.0000",
        "average_loss_r": "-1.0000",
        "total_pnl": "50.00000000",
        "total_fees": "0.00000000",
        "largest_win": "100.00000000",
        "largest_loss": "-50.00000000",
        "average_hold_time": "P5DT5H30M",
        "average_hold_time_winners": "P4DT5H30M",
        "average_hold_time_losers": "P5DT5H30M",
        "plan_adherence_rate": "0.6667",
        "max_drawdown": "50.00000000",
    }


def test_summary_without_trades_is_null_not_zero(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    summary = get(api_client, "/analytics/summary", headers)
    assert summary["trade_count"] == 0
    assert summary["win_rate"] is None
    assert summary["expectancy"] is None
    assert summary["average_hold_time"] is None
    assert summary["total_pnl"] == "0.00000000"  # fixed-point, never "0E-8"
    assert summary["max_drawdown"] == "0.00000000"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"start_date": "2026-10-06"}, {"loss", "breakeven"}),
        ({"end_date": "2026-10-06"}, {"win", "loss"}),  # the end date is inclusive
        ({"start_date": "2026-10-06", "end_date": "2026-10-06"}, {"loss"}),
        ({"symbol": "msft"}, {"loss"}),  # normalized like everywhere else
        ({"side": "short"}, {"breakeven"}),
        ({"asset_type": "etf"}, set()),
        ({"source": "manual"}, {"win", "loss", "breakeven"}),
    ],
)
def test_summary_filters(
    api_client: TestClient, book: dict[str, Any], params: dict[str, str], expected: set[str]
) -> None:
    curve = get(api_client, "/analytics/equity-curve", book["headers"], **params)
    assert {p["trade_id"] for p in curve} == {book[name]["id"] for name in expected}
    summary = get(api_client, "/analytics/summary", book["headers"], **params)
    assert summary["trade_count"] == len(expected)


def test_filter_by_strategy(api_client: TestClient, book: dict[str, Any]) -> None:
    summary = get(
        api_client, "/analytics/summary", book["headers"], strategy_id=book["strategy"]["id"]
    )
    assert (summary["wins"], summary["losses"]) == (1, 1)


def test_the_date_range_covers_whole_utc_days(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    last_second = create_closed_trade(
        api_client, headers, exit_price="110", exit_at="2026-10-06T23:59:59Z"
    )
    create_closed_trade(api_client, headers, exit_price="110", exit_at="2026-10-07T00:00:00Z")
    curve = get(api_client, "/analytics/equity-curve", headers, end_date="2026-10-06")
    assert [p["trade_id"] for p in curve] == [last_second["id"]]


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-10-07", "end_date": "2026-10-06"},
        {"start_date": "06/10/2026"},
        {"side": "sideways"},
    ],
)
def test_bad_filters_are_422(api_client: TestClient, params: dict[str, str]) -> None:
    _, headers = registered_headers(api_client)
    for path in ("/analytics/summary", "/analytics/equity-curve", "/analytics/frequency"):
        assert api_client.get(path, params=params, headers=headers).status_code == 422


def test_analytics_need_a_token(api_client: TestClient) -> None:
    for path in ("summary", "equity-curve", "breakdown?by=side", "frequency"):
        assert api_client.get(f"/analytics/{path}").status_code == 401


# --- equity curve ----------------------------------------------------------------


def test_equity_curve(api_client: TestClient, book: dict[str, Any]) -> None:
    curve = get(api_client, "/analytics/equity-curve", book["headers"])
    assert curve == [
        {
            "trade_id": book["win"]["id"],
            "exit_at": "2026-10-05T20:00:00Z",
            "pnl": "100.00000000",
            "cumulative_pnl": "100.00000000",
        },
        {
            "trade_id": book["loss"]["id"],
            "exit_at": "2026-10-06T20:00:00Z",
            "pnl": "-50.00000000",
            "cumulative_pnl": "50.00000000",
        },
        {
            "trade_id": book["breakeven"]["id"],
            "exit_at": "2026-10-07T20:00:00Z",
            "pnl": "0.00000000",
            "cumulative_pnl": "50.00000000",
        },
    ]


# --- breakdown -------------------------------------------------------------------


def test_breakdown_by_strategy(api_client: TestClient, book: dict[str, Any]) -> None:
    groups = get(api_client, "/analytics/breakdown", book["headers"], by="strategy")
    assert [(g["key"], g["label"], g["summary"]["trade_count"]) for g in groups] == [
        (book["strategy"]["id"], "Breakout", 2),
        (None, "No strategy", 1),
    ]
    assert groups[0]["summary"]["total_pnl"] == "50.00000000"


@pytest.mark.parametrize(
    ("by", "expected"),
    [
        ("side", [("long", 2), ("short", 1)]),
        ("symbol", [("AAPL", 2), ("MSFT", 1)]),
        ("asset_type", [("stock", 3)]),
        ("exposure", [("bullish", 2), ("bearish", 1)]),
    ],
)
def test_breakdown_groups_biggest_first(
    api_client: TestClient, book: dict[str, Any], by: str, expected: list[tuple[str, int]]
) -> None:
    groups = get(api_client, "/analytics/breakdown", book["headers"], by=by)
    assert [(g["key"], g["summary"]["trade_count"]) for g in groups] == expected
    assert all(g["label"] == g["key"] for g in groups)


def test_breakdown_by_exposure_groups_inverse_etfs_with_shorts(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    create_closed_trade(api_client, headers, exit_price="110", exit_at="2026-10-05T20:00:00Z")
    create_closed_trade(
        api_client,
        headers,
        exit_price="110",
        exit_at="2026-10-05T20:00:00Z",
        symbol="SQQQ",
        asset_type="etf",
        leverage_factor=-3,
    )
    create_closed_trade(
        api_client,
        headers,
        exit_price="90",
        exit_at="2026-10-05T20:00:00Z",
        side="short",
        planned_stop="105.00",
        planned_target="85.00",
    )
    groups = get(api_client, "/analytics/breakdown", headers, by="exposure")
    assert [(g["key"], g["summary"]["trade_count"]) for g in groups] == [
        ("bearish", 2),
        ("bullish", 1),
    ]


@pytest.mark.parametrize("params", [{}, {"by": "weekday"}])
def test_breakdown_needs_a_valid_by(api_client: TestClient, params: dict[str, str]) -> None:
    _, headers = registered_headers(api_client)
    assert api_client.get("/analytics/breakdown", params=params, headers=headers).status_code == 422


# --- frequency -------------------------------------------------------------------


def test_frequency_counts_opened_trades_per_week(
    api_client: TestClient, book: dict[str, Any]
) -> None:
    # The three closed trades and the open one were all entered in W40; planned and
    # cancelled trades were never opened.
    assert get(api_client, "/analytics/frequency", book["headers"]) == [
        {"week": "2026-W40", "week_start": "2026-09-28", "trades_opened": 4}
    ]


def test_frequency_fills_empty_weeks(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    for entry_at in ("2026-09-14T14:30:00Z", "2026-10-01T14:30:00Z"):
        create_closed_trade(
            api_client, headers, exit_price="110", exit_at="2026-10-05T20:00:00Z", entry_at=entry_at
        )
    weeks = get(api_client, "/analytics/frequency", headers)
    assert [(w["week"], w["trades_opened"]) for w in weeks] == [
        ("2026-W38", 1),
        ("2026-W39", 0),
        ("2026-W40", 1),
    ]
    # With a date range, the range sets the weeks, and dates filter on entry.
    weeks = get(
        api_client, "/analytics/frequency", headers, start_date="2026-09-20", end_date="2026-10-13"
    )
    assert [(w["week"], w["trades_opened"]) for w in weeks] == [
        ("2026-W38", 0),
        ("2026-W39", 0),
        ("2026-W40", 1),
        ("2026-W41", 0),
        ("2026-W42", 0),
    ]


# --- ownership -------------------------------------------------------------------


def test_another_users_trades_are_invisible(api_client: TestClient, book: dict[str, Any]) -> None:
    _, other = registered_headers(api_client)
    assert get(api_client, "/analytics/summary", other)["trade_count"] == 0
    assert get(api_client, "/analytics/equity-curve", other) == []
    assert get(api_client, "/analytics/breakdown", other, by="strategy") == []
    assert get(api_client, "/analytics/frequency", other) == []
    # Even when filtering by the first user's strategy id.
    summary = get(api_client, "/analytics/summary", other, strategy_id=book["strategy"]["id"])
    assert summary["trade_count"] == 0
