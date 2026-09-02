"""Shared-fixture tests — task P1-BE-18.

A single test exercises all four conftest fixtures; two more prove the ``db``
fixture rolls back between tests (so no state bleeds between tests or runs).
"""

from __future__ import annotations

from sqlalchemy import text

_INSERT_SNAPSHOT = text(
    "INSERT INTO portfolio_snapshots "
    "(cycle_id, ts, total_value, cash, equity, buying_power) "
    "VALUES (:cycle_id, '2026-09-03 00:00:00', 1, 1, 1, 1)"
)
_COUNT_SNAPSHOTS = text("SELECT count(*) FROM portfolio_snapshots")


def test_all_four_fixtures(db, client, mock_llm, mock_alpaca) -> None:
    # db — a live, queryable session
    assert db.execute(text("SELECT 1")).scalar() == 1

    # client — the wired app answers
    assert client.get("/health").status_code == 200
    assert client.get("/context").status_code == 200

    # mock_llm — patched over backend.llm, records calls, no network
    from backend.llm.provider import get_llm_client

    completion = get_llm_client().chat.completions.create(
        model="x", messages=[{"role": "user", "content": "hi"}]
    )
    assert completion.choices[0].message.content
    assert mock_llm.calls, "mock_llm did not record the call"

    # mock_alpaca — patched over the Alpaca client, canned payloads
    from backend.integrations.alpaca.client import AlpacaClient

    account = AlpacaClient().get_account()
    assert account["id"] == "mock-acct"
    assert AlpacaClient().get_positions()[0]["symbol"] == "AAPL"


def test_db_write_is_visible_within_the_test(db) -> None:
    assert db.execute(_COUNT_SNAPSHOTS).scalar() == 0
    db.execute(_INSERT_SNAPSHOT, {"cycle_id": "fixtures-1"})
    db.flush()
    assert db.execute(_COUNT_SNAPSHOTS).scalar() == 1


def test_db_is_rolled_back_before_the_next_test(db) -> None:
    # the row written by the previous test must not survive
    assert db.execute(_COUNT_SNAPSHOTS).scalar() == 0
