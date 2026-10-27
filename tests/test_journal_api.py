from typing import Any

import pytest
from fastapi.testclient import TestClient

from api_helpers import create_entry, create_trade, registered_headers
from trading_journal.domain.enums import JournalPhase, TradeStatus
from trading_journal.domain.journal_rules import ALLOWED_PHASES, DEFAULT_PHASE


def test_create_and_list(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    entry = create_entry(api_client, headers, trade["id"], body="  Setup looks clean.  ")
    listed = api_client.get(f"/trades/{trade['id']}/journal", headers=headers)

    assert entry["phase"] == "pre"
    assert entry["body"] == "Setup looks clean."  # trimmed
    assert entry["trade_id"] == trade["id"]
    assert set(entry) == {"id", "trade_id", "phase", "body", "created_at", "updated_at"}
    assert listed.status_code == 200
    assert listed.json() == [entry]


def test_entries_are_listed_oldest_first_and_filterable(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status="closed")
    bodies = ["first", "second", "third"]
    phases = ["pre", "post", "pre"]
    for body, phase in zip(bodies, phases, strict=True):
        create_entry(api_client, headers, trade["id"], body=body, phase=phase)

    everything = api_client.get(f"/trades/{trade['id']}/journal", headers=headers).json()
    pre_only = api_client.get(
        f"/trades/{trade['id']}/journal", params={"phase": "pre"}, headers=headers
    ).json()

    assert [e["body"] for e in everything] == bodies
    assert [e["body"] for e in pre_only] == ["first", "third"]


def test_entries_belong_to_their_trade(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    one, two = create_trade(api_client, headers), create_trade(api_client, headers)
    create_entry(api_client, headers, one["id"], body="about one")

    listed = api_client.get(f"/trades/{two['id']}/journal", headers=headers)

    assert listed.json() == []


# --- the phase rule (ADR 0010) ------------------------------------------------------

STATUSES = [s.value for s in TradeStatus]
PHASES = [p.value for p in JournalPhase]


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("status", STATUSES)
def test_phase_matrix(api_client: TestClient, status: str, phase: str) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status=status)

    response = api_client.post(
        f"/trades/{trade['id']}/journal", json={"phase": phase, "body": "note"}, headers=headers
    )

    if JournalPhase(phase) in ALLOWED_PHASES[TradeStatus(status)]:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 409
        assert response.json()["detail"].endswith(f"this one is {status}")


@pytest.mark.parametrize("status", STATUSES)
def test_default_phase_follows_the_trade(api_client: TestClient, status: str) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status=status)

    entry = create_entry(api_client, headers, trade["id"])

    assert entry["phase"] == DEFAULT_PHASE[TradeStatus(status)].value


def test_backfilling_a_pre_note_after_close(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status="closed")

    entry = create_entry(
        api_client, headers, trade["id"], body="What I saw before entry", phase="pre"
    )

    assert entry["phase"] == "pre"


# --- update and delete -----------------------------------------------------------------


def test_patch_body(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)
    entry = create_entry(api_client, headers, trade["id"], body="tyop")

    response = api_client.patch(f"/journal/{entry['id']}", json={"body": "typo"}, headers=headers)
    listed = api_client.get(f"/trades/{trade['id']}/journal", headers=headers).json()

    assert response.status_code == 200
    updated = response.json()
    assert updated["body"] == "typo"
    assert updated["phase"] == "pre"  # unchanged
    assert updated["updated_at"] >= updated["created_at"]
    assert listed == [updated]


def test_patch_phase_follows_the_same_rule(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers, status="open")
    entry = create_entry(api_client, headers, trade["id"], phase="pre")

    to_during = api_client.patch(
        f"/journal/{entry['id']}", json={"phase": "during"}, headers=headers
    )
    to_post = api_client.patch(f"/journal/{entry['id']}", json={"phase": "post"}, headers=headers)

    assert to_during.status_code == 200
    assert to_post.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"body": "   "}, id="blank-body"),
        pytest.param({"body": "x" * 20_001}, id="body-too-long"),
        pytest.param({"phase": "after"}, id="unknown-phase"),
        pytest.param({"phase": None}, id="null-phase"),
        pytest.param({"body": None}, id="null-body"),
        pytest.param({"mood": "great"}, id="unknown-field"),
    ],
)
def test_invalid_patch_is_rejected(api_client: TestClient, payload: dict[str, Any]) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)
    entry = create_entry(api_client, headers, trade["id"])

    response = api_client.patch(f"/journal/{entry['id']}", json=payload, headers=headers)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-body"),
        pytest.param({"body": ""}, id="empty-body"),
        pytest.param({"body": "ok", "trade_id": "x"}, id="unknown-field"),
    ],
)
def test_invalid_create_is_rejected(api_client: TestClient, payload: dict[str, Any]) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)

    response = api_client.post(f"/trades/{trade['id']}/journal", json=payload, headers=headers)

    assert response.status_code == 422


def test_delete(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)
    keep = create_entry(api_client, headers, trade["id"], body="keep")
    drop = create_entry(api_client, headers, trade["id"], body="drop")

    response = api_client.delete(f"/journal/{drop['id']}", headers=headers)
    again = api_client.delete(f"/journal/{drop['id']}", headers=headers)

    assert response.status_code == 204
    assert again.status_code == 404
    assert api_client.get(f"/trades/{trade['id']}/journal", headers=headers).json() == [keep]


def test_deleting_a_trade_deletes_its_journal(api_client: TestClient) -> None:
    _, headers = registered_headers(api_client)
    trade = create_trade(api_client, headers)
    entry = create_entry(api_client, headers, trade["id"])

    api_client.delete(f"/trades/{trade['id']}", headers=headers)

    assert api_client.get(f"/trades/{trade['id']}/journal", headers=headers).status_code == 404
    patch = api_client.patch(f"/journal/{entry['id']}", json={"body": "x"}, headers=headers)
    assert patch.status_code == 404
