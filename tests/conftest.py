"""Pytest configuration and global fixtures.

Task P1-BE-18 adds the four shared fixtures the rest of the suite builds on:

``db``
    A transactional SQLAlchemy :class:`~sqlalchemy.orm.Session` on a throwaway
    SQLite database migrated to head once per session. Every test runs inside a
    transaction that is rolled back on teardown, so writes never leak between
    tests or between runs.
``client``
    A :class:`fastapi.testclient.TestClient` for the fully-wired app.
``mock_llm``
    A stand-in for the OpenAI-compatible LLM client, patched over
    ``backend.llm`` so no network call is made.
``mock_alpaca``
    A stand-in for :class:`backend.integrations.alpaca.AlpacaClient` returning
    canned account / position payloads.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


@pytest.fixture(scope="session")
def event_loop_policy():
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


# --------------------------------------------------------------------------- #
# db — transactional session on a migrated scratch SQLite database
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def _migrated_sqlite_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Create a scratch SQLite DB, migrate it to head, and return its URL."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    url = f"sqlite:///{db_path}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, "ALEMBIC_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed for the test DB:\n{result.stdout}\n{result.stderr}"
    )
    return url


@pytest.fixture
def db(_migrated_sqlite_url: str) -> Iterator[Any]:
    """Yield a Session wrapped in a transaction that is rolled back on teardown."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session

    engine = create_engine(_migrated_sqlite_url)

    @event.listens_for(engine, "connect")
    def _enforce_sqlite_fks(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()
        engine.dispose()


# --------------------------------------------------------------------------- #
# client — TestClient for the wired FastAPI app
# --------------------------------------------------------------------------- #


@pytest.fixture
def client() -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from backend.api import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# mock_llm — offline OpenAI-compatible client
# --------------------------------------------------------------------------- #


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.role = "assistant"
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.index = 0
        self.finish_reason = "stop"
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.id = "chatcmpl-mock"
        self.model = "mock-model"
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, owner: "FakeLLMClient") -> None:
        self._owner = owner

    def create(self, **kwargs: Any) -> _FakeCompletion:
        self._owner.calls.append(kwargs)
        return _FakeCompletion(self._owner.response_content)


class _FakeChat:
    def __init__(self, owner: "FakeLLMClient") -> None:
        self.completions = _FakeCompletions(owner)


class FakeLLMClient:
    """Minimal stand-in for the ``openai.OpenAI`` client used by the backend."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response_content = '{"ok": true}'
        self.chat = _FakeChat(self)


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLMClient:
    fake = FakeLLMClient()
    monkeypatch.setattr("backend.llm.provider.get_llm_client", lambda *a, **k: fake)
    monkeypatch.setattr("backend.llm.get_llm_client", lambda *a, **k: fake, raising=False)
    return fake


# --------------------------------------------------------------------------- #
# mock_alpaca — offline Alpaca trading client
# --------------------------------------------------------------------------- #


class FakeAlpacaClient:
    """Stand-in for :class:`backend.integrations.alpaca.AlpacaClient`."""

    ACCOUNT: dict[str, Any] = {
        "id": "mock-acct",
        "account_number": "PA000MOCK",
        "status": "ACTIVE",
        "currency": "USD",
        "cash": "100000.00",
        "portfolio_value": "250000.00",
        "buying_power": "200000.00",
    }
    POSITIONS: list[dict[str, Any]] = [
        {
            "symbol": "AAPL",
            "qty": "100",
            "avg_entry_price": "150.00",
            "market_value": "18000.00",
            "asset_class": "us_equity",
            "side": "long",
            "unrealized_pl": "3000.00",
        }
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.paper = True
        self.base_url = "https://paper-api.alpaca.markets"
        self.calls: list[str] = []

    def get_account(self) -> dict[str, Any]:
        self.calls.append("get_account")
        return dict(self.ACCOUNT)

    def get_positions(self) -> list[dict[str, Any]]:
        self.calls.append("get_positions")
        return [dict(p) for p in self.POSITIONS]

    def close(self) -> None:
        self.calls.append("close")

    def __enter__(self) -> "FakeAlpacaClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@pytest.fixture
def mock_alpaca(monkeypatch: pytest.MonkeyPatch) -> FakeAlpacaClient:
    fake = FakeAlpacaClient()
    monkeypatch.setattr(
        "backend.integrations.alpaca.client.AlpacaClient", lambda *a, **k: fake
    )
    monkeypatch.setattr(
        "backend.integrations.alpaca.AlpacaClient", lambda *a, **k: fake, raising=False
    )
    return fake
