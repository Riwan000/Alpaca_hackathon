"""POST /monitor + demo scheduler — task P7-BE-9 / issue #177.

Confirms:
- a manual tick returns the fired triggers (or none) and the escalation verdict;
- the tick persists ``monitoring_events`` / ``monitoring_state`` so the read-back
  endpoints reflect it;
- a tick with no available context still answers (no 500);
- the demo scheduler registers its job.
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.monitor import (
    DEMO_TICK_JOB_ID,
    MonitorScheduler,
    get_monitor_context,
    install_demo_monitor_tick,
)
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.models.common import OptionLeg
from backend.models.enums import OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _ctx(*, hedge_ratio: float, target: float, volatility: float, drawdown: float) -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    exp = (now + _dt.timedelta(days=30)).date()
    return HedgeContext(
        cycle_id="cyc-monitor-api",
        timestamp=now,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05, drawdown_tolerance_pct=0.10, target_hedge_ratio=target
        ),
        portfolio_state=PortfolioState(
            total_value=250_000.0, cash=100_000.0, equity=150_000.0, buying_power=120_000.0,
            drawdown=drawdown, volatility=volatility, beta=1.0, gross_exposure=0.6,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=14.0, index_trend="UP"),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target,
            expiration=exp,
            hedge_pnl=100.0,
            legs=[
                OptionLeg(
                    underlying="AAPL", right=OptionRight.PUT, side=OrderSide.BUY,
                    strike=150.0, expiration=exp, quantity=4,
                )
            ],
        ),
    )


_DRIFT_CTX = lambda _cid=None: _ctx(hedge_ratio=0.80, target=0.40, volatility=0.11, drawdown=-0.004)  # noqa: E731
_CALM_CTX = lambda _cid=None: _ctx(hedge_ratio=0.50, target=0.50, volatility=0.11, drawdown=-0.004)  # noqa: E731


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_url = f"sqlite:///{tmp_path / 'monitor_api.db'}"
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    with TestClient(app) as c:
        c.app = app  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_manual_tick_reports_fired_triggers(client: TestClient) -> None:
    client.app.dependency_overrides[get_monitor_context] = lambda: _DRIFT_CTX  # type: ignore[attr-defined]

    res = client.post("/monitor", json={"cycle_id": "cyc-monitor-api"})
    assert res.status_code == 200, res.text
    body = res.json()

    assert "PORTFOLIO_DELTA" in body["active_triggers"]
    assert body["triggers"] and any(t["trigger_type"] == "PORTFOLIO_DELTA" for t in body["triggers"])
    assert body["escalate"] is True
    assert body["persisted"] is True

    # the tick persisted its events — the read-back endpoint sees them
    events = client.get("/monitoring/events", params={"cycle_id": "cyc-monitor-api"}).json()
    assert any(e["trigger_type"] == "PORTFOLIO_DELTA" for e in events)


def test_manual_tick_with_no_triggers_is_all_clear(client: TestClient) -> None:
    client.app.dependency_overrides[get_monitor_context] = lambda: _CALM_CTX  # type: ignore[attr-defined]

    body = client.post("/monitor").json()

    assert body["triggers"] == []
    assert body["active_triggers"] == []
    assert body["escalate"] is False


def test_manual_tick_without_context_still_answers(client: TestClient) -> None:
    client.app.dependency_overrides[get_monitor_context] = lambda: (lambda _cid=None: None)  # type: ignore[attr-defined]

    res = client.post("/monitor")
    assert res.status_code == 200
    body = res.json()
    assert body["triggers"] == []
    assert body["escalate"] is False
    assert body["note"]


# --------------------------------------------------------------------------- #
# scheduler
# --------------------------------------------------------------------------- #


def test_scheduler_registers_a_job() -> None:
    sched = MonitorScheduler()
    hits = {"n": 0}

    job = sched.register("demo-tick", 300.0, lambda: hits.__setitem__("n", hits["n"] + 1))

    assert "demo-tick" in sched.jobs
    assert sched.jobs["demo-tick"].interval_seconds == 300.0
    assert job.fn is sched.jobs["demo-tick"].fn
    assert sched.running is False  # register does not start


def test_install_demo_monitor_tick_registers_under_known_id() -> None:
    sched = MonitorScheduler()

    install_demo_monitor_tick(sched, interval_seconds=120.0, tick=lambda: None)

    assert DEMO_TICK_JOB_ID in sched.jobs
    assert sched.jobs[DEMO_TICK_JOB_ID].interval_seconds == 120.0


def test_scheduler_start_fires_then_stops() -> None:
    sched = MonitorScheduler()
    hits = {"n": 0}
    sched.register("fast", 0.05, lambda: hits.__setitem__("n", hits["n"] + 1))

    sched.start()
    try:
        deadline = _dt.datetime.now() + _dt.timedelta(seconds=2)
        while hits["n"] < 1 and _dt.datetime.now() < deadline:
            pass
    finally:
        sched.stop()

    assert hits["n"] >= 1
    assert sched.running is False


# --------------------------------------------------------------------------- #
# create_app() startup/shutdown wiring — ``Settings.enable_monitor_scheduler``
# --------------------------------------------------------------------------- #


class _FakeSchedulerSettings:
    """Just enough of :class:`~backend.config.Settings` for the startup hook."""

    def __init__(self, enable_monitor_scheduler: bool) -> None:
        self.enable_monitor_scheduler = enable_monitor_scheduler


@pytest.fixture
def isolated_scheduler(monkeypatch: pytest.MonkeyPatch) -> MonitorScheduler:
    """Swap the process-wide scheduler singleton for a throwaway one.

    ``create_app()``'s startup/shutdown hooks call
    :func:`backend.api.monitor.get_monitor_scheduler` /
    :func:`~backend.api.monitor.install_demo_monitor_tick`, both of which resolve
    the module-level ``_SCHEDULER`` — patch that so this test never touches (or
    is affected by) the real singleton other tests in this module use.
    """
    import backend.api.monitor as monitor_module

    fresh = MonitorScheduler()
    monkeypatch.setattr(monitor_module, "_SCHEDULER", fresh)
    return fresh


def test_create_app_does_not_start_scheduler_by_default(
    monkeypatch: pytest.MonkeyPatch, isolated_scheduler: MonitorScheduler
) -> None:
    """``enable_monitor_scheduler`` defaults off — no tick fires without opt-in."""
    monkeypatch.setattr(
        "backend.config.get_settings", lambda: _FakeSchedulerSettings(False)
    )

    with TestClient(create_app()):
        assert isolated_scheduler.running is False
        assert DEMO_TICK_JOB_ID not in isolated_scheduler.jobs


def test_create_app_starts_scheduler_when_enabled(
    monkeypatch: pytest.MonkeyPatch, isolated_scheduler: MonitorScheduler
) -> None:
    """The flag on: the demo tick is registered and the scheduler is running,
    and it is stopped again on shutdown."""
    monkeypatch.setattr(
        "backend.config.get_settings", lambda: _FakeSchedulerSettings(True)
    )

    with TestClient(create_app()):
        assert isolated_scheduler.running is True
        assert DEMO_TICK_JOB_ID in isolated_scheduler.jobs

    assert isolated_scheduler.running is False
