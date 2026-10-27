"""GET /reviews/weekly (ADR 0012)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import create_closed_trade, create_entry, create_trade, registered_headers
from trading_journal.domain.iso_week import week_label


def review(client: TestClient, headers: dict[str, str], week: str | None = None) -> Any:
    params = {"week": week} if week else {}
    response = client.get("/reviews/weekly", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_week_runs_monday_to_monday_utc(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    sunday = create_closed_trade(
        api_client,
        headers,
        exit_price="110",
        exit_at="2026-10-18T23:59:59Z",  # the last second of 2026-W42
        entry_at="2026-10-15T14:30:00Z",
    )
    monday = create_closed_trade(
        api_client,
        headers,
        exit_price="95",
        exit_at="2026-10-19T00:00:00Z",  # the first second of 2026-W43
        entry_at="2026-10-15T14:30:00Z",
    )

    w42 = review(api_client, headers, "2026-W42")
    assert w42["week"] == "2026-W42"
    assert w42["starts_at"] == "2026-10-12T00:00:00Z"
    assert w42["ends_at"] == "2026-10-19T00:00:00Z"
    assert [t["trade"]["id"] for t in w42["closed"]] == [sunday["id"]]
    assert w42["summary"]["trade_count"] == 1
    assert w42["summary"]["total_pnl"] == "100.00000000"

    w43 = review(api_client, headers, "2026-W43")
    assert [t["trade"]["id"] for t in w43["closed"]] == [monday["id"]]
    assert w43["summary"]["losses"] == 1


def test_this_weeks_review_has_closed_and_cancelled_trades_with_their_journals(
    api_client: TestClient,
) -> None:
    _, headers = registered_headers(api_client)
    now = datetime.now(UTC)
    closed = create_closed_trade(
        api_client,
        headers,
        exit_price="110",
        exit_at=now.isoformat(),
        entry_at=now.isoformat(),
        followed_plan=False,
    )
    cancelled = create_trade(api_client, headers, status="cancelled", symbol="NVDA")
    create_trade(api_client, headers, status="open")  # neither closed nor cancelled
    create_trade(api_client, headers)  # planned

    pre = create_entry(api_client, headers, closed["id"], "Plan looks clean.", phase="pre")
    during = create_entry(api_client, headers, closed["id"], "Moved my stop.", phase="during")
    post_1 = create_entry(api_client, headers, closed["id"], "Broke my rule.", phase="post")
    post_2 = create_entry(api_client, headers, closed["id"], "Next time, no.", phase="post")
    skipped = create_entry(api_client, headers, cancelled["id"], "Gap up, skipped.", phase="pre")

    week = review(api_client, headers)  # no week: the current one
    assert week["week"] == week_label(now.date())
    assert cancelled["cancelled_at"] is not None

    [closed_item] = week["closed"]
    assert closed_item["trade"]["id"] == closed["id"]
    assert closed_item["trade"]["pnl"] == "100.00000000"
    journal = closed_item["journal"]
    assert [e["id"] for e in journal["pre"]] == [pre["id"]]
    assert [e["id"] for e in journal["during"]] == [during["id"]]
    assert [e["id"] for e in journal["post"]] == [post_1["id"], post_2["id"]]  # oldest first

    [cancelled_item] = week["cancelled"]
    assert cancelled_item["trade"]["id"] == cancelled["id"]
    assert cancelled_item["journal"] == {"pre": [skipped], "during": [], "post": []}

    # The summary covers the closed trades only.
    assert week["summary"]["trade_count"] == 1
    assert week["summary"]["plan_adherence_rate"] == "0.0000"


def test_an_empty_week(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    week = review(api_client, headers, "2026-W01")
    assert week["closed"] == []
    assert week["cancelled"] == []
    assert week["summary"]["trade_count"] == 0
    assert week["summary"]["win_rate"] is None


@pytest.mark.parametrize("week", ["2025-W53", "2026-W00", "2026-W54", "2026-42", "2026-W4", "x"])
def test_a_bad_week_is_422(api_client: TestClient, week: str) -> None:
    _, headers = registered_headers(api_client)
    response = api_client.get("/reviews/weekly", params={"week": week}, headers=headers)
    assert response.status_code == 422


def test_the_review_needs_a_token(api_client: TestClient) -> None:
    assert api_client.get("/reviews/weekly").status_code == 401


def test_another_users_week_is_invisible(api_client: TestClient) -> None:
    _, owner = registered_headers(api_client)
    trade = create_closed_trade(api_client, owner, exit_price="110", exit_at="2026-10-14T20:00:00Z")
    create_entry(api_client, owner, trade["id"], "Mine.", phase="post")
    create_trade(api_client, owner, status="cancelled")

    _, other = registered_headers(api_client)
    assert review(api_client, other, "2026-W42")["closed"] == []
    assert review(api_client, other)["cancelled"] == []
    assert [t["trade"]["id"] for t in review(api_client, owner, "2026-W42")["closed"]] == [
        trade["id"]
    ]
