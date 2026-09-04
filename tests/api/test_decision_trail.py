"""Decision-trail endpoint tests — task P8-BE-4.

``GET /decision-trail/{order_id}`` walks one trade back through its cycle:
order → risk approval → strategy decision → hypotheses → analysis context →
trigger. A complete cycle returns every hop linked; a cycle with a gap returns
the partial chain with the gap named in ``missing_links`` (never silently
dropped); an unknown order id 404s.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from backend.api import create_app
from backend.api.readback import get_readback_engine
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.monitoring_repo import (
    MonitoringEventRecord,
    MonitoringRepository,
    ReassessmentEventRecord,
)
from backend.db.orders_repo import FillRecord, OrderRecord, OrderRepository
from backend.db.repository import (
    PortfolioSnapshotRecord,
    PortfolioSnapshotRepository,
    PositionRecord,
)
from backend.db.risk_checks_repo import RiskCheckRecord, RiskCheckRepository
from backend.db.strategy_repo import (
    StrategyDecisionRecord,
    StrategyDecisionRepository,
    StrategyHypothesisRecord,
    StrategyHypothesisRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


class _Seeded:
    """The order ids the fixture wrote, keyed by scenario."""

    complete_order_id: int
    gapped_order_id: int


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App wired to a scratch DB holding one complete cycle and one with gaps."""
    db_url = f"sqlite:///{tmp_path / 'decision_trail_scratch.db'}"
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url), future=True)

    snapshots = PortfolioSnapshotRepository(engine)
    hypotheses = StrategyHypothesisRepository(engine)
    decisions = StrategyDecisionRepository(engine)
    risk = RiskCheckRepository(engine)
    orders = OrderRepository(engine)
    monitoring = MonitoringRepository(engine)

    # ---- cycle_full: every hop present -------------------------------------- #
    snapshots.save_with_positions(
        PortfolioSnapshotRecord(
            cycle_id="cycle_full",
            total_value=Decimal("250000.0000"),
            cash=Decimal("100000.0000"),
            equity=Decimal("150000.0000"),
            buying_power=Decimal("200000.0000"),
            volatility=Decimal("0.2800"),
            beta=Decimal("1.1500"),
            drawdown=Decimal("-0.0600"),
        ),
        [
            PositionRecord(
                symbol="AAPL",
                qty=Decimal("200.0000"),
                avg_price=Decimal("150.0000"),
                market_value=Decimal("30000.0000"),
                asset_class="us_equity",
                side="long",
            )
        ],
    )
    saved_hyps = hypotheses.save_many(
        [
            StrategyHypothesisRecord(
                cycle_id="cycle_full",
                strategy_type="PROTECTIVE_PUT",
                verdict="ACCEPTED",
                legs=[{"symbol": "AAPL260320P00145000", "side": "BUY"}],
                metrics={"cost": 315.0},
            ),
            StrategyHypothesisRecord(
                cycle_id="cycle_full",
                strategy_type="NO_HEDGE",
                verdict="REJECTED",
                rejection_reason="drawdown already breached tolerance",
            ),
        ]
    )
    selected = saved_hyps[0]
    decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_full",
            action="HEDGE",
            rationale="Protective put is the cheapest way back under the floor.",
            selected_hypothesis_id=selected.id,
            alternatives=[{"strategy_type": "NO_HEDGE"}],
            comparison=[{"strategy_type": "PROTECTIVE_PUT", "score": 0.82}],
        )
    )
    risk.create(
        RiskCheckRecord(
            cycle_id="cycle_full",
            verdict="APPROVE",
            checks=[{"name": "hedge_budget", "category": "COST", "passed": True}],
        )
    )
    full_order = orders.save_with_fills(
        OrderRecord(
            cycle_id="cycle_full",
            order_class="MLEG",
            status="FILLED",
            legs=[{"symbol": "AAPL260320P00145000", "side": "BUY"}],
            broker_order_id="alpaca-full-1",
        ),
        [
            FillRecord(
                order_id=0,
                leg_symbol="AAPL260320P00145000",
                qty=Decimal("1"),
                price=Decimal("3.15"),
                slippage=Decimal("0.02"),
            )
        ],
    )
    event = monitoring.record_event(
        MonitoringEventRecord(
            cycle_id="cycle_full",
            trigger_type="DRAWDOWN_LIMIT",
            observed={"drawdown": -0.06},
            threshold=Decimal("-0.0500"),
        )
    )
    monitoring.record_reassessment(
        ReassessmentEventRecord(
            cycle_id="cycle_full",
            trigger_event_id=event.id,
            outcome="INCREASE_HEDGE",
            reason="Drawdown limit breached; add downside protection.",
            context={"level": 2},
        )
    )

    # ---- cycle_gap: no analysis context, no trigger ----------------------- #
    hypotheses.save_many(
        [
            StrategyHypothesisRecord(
                cycle_id="cycle_gap",
                strategy_type="PUT_SPREAD",
                verdict="ACCEPTED",
            )
        ]
    )
    decisions.create(
        StrategyDecisionRecord(
            cycle_id="cycle_gap",
            action="HEDGE",
            rationale="Put spread caps cost.",
        )
    )
    risk.create(RiskCheckRecord(cycle_id="cycle_gap", verdict="APPROVE"))
    gap_order = orders.create(
        OrderRecord(cycle_id="cycle_gap", order_class="MLEG", status="SUBMITTED")
    )

    _Seeded.complete_order_id = int(full_order.order.id)  # type: ignore[arg-type]
    _Seeded.gapped_order_id = int(gap_order.id)  # type: ignore[arg-type]

    app = create_app()
    app.dependency_overrides[get_readback_engine] = lambda: engine
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_full_chain_is_linked(client: TestClient) -> None:
    res = client.get(f"/decision-trail/{_Seeded.complete_order_id}")
    assert res.status_code == 200, res.text
    trail = res.json()

    assert trail["order_id"] == _Seeded.complete_order_id
    assert trail["cycle_id"] == "cycle_full"
    assert trail["complete"] is True
    assert trail["missing_links"] == []

    # order → its fills
    assert trail["order"]["status"] == "FILLED"
    assert trail["order"]["broker_order_id"] == "alpaca-full-1"
    assert len(trail["order"]["fills"]) == 1

    # risk approval
    assert trail["risk_approval"]["verdict"] == "APPROVE"
    assert trail["risk_approval"]["cycle_id"] == "cycle_full"

    # strategy decision → selected hypothesis
    decision = trail["strategy_decision"]
    assert decision["action"] == "HEDGE"
    selected_id = decision["selected_hypothesis_id"]
    assert selected_id is not None

    # hypotheses (both the accepted and the rejected one), selected flagged
    hyps = trail["hypotheses"]
    assert {h["strategy_type"] for h in hyps} == {"PROTECTIVE_PUT", "NO_HEDGE"}
    selected = [h for h in hyps if h["selected"]]
    assert len(selected) == 1
    assert selected[0]["id"] == selected_id
    assert selected[0]["strategy_type"] == "PROTECTIVE_PUT"

    # analysis context
    ctx = trail["analysis_context"]
    assert ctx["cycle_id"] == "cycle_full"
    assert ctx["total_value"] == 250000.0
    assert [p["symbol"] for p in ctx["positions"]] == ["AAPL"]

    # trigger — the Level-1 event and the Level-2 reassessment that links it
    trigger = trail["trigger"]
    assert len(trigger["monitoring_events"]) == 1
    assert trigger["monitoring_events"][0]["trigger_type"] == "DRAWDOWN_LIMIT"
    assert len(trigger["reassessments"]) == 1
    assert (
        trigger["reassessments"][0]["trigger_event_id"]
        == trigger["monitoring_events"][0]["id"]
    )


def test_missing_link_is_reported_not_dropped(client: TestClient) -> None:
    res = client.get(f"/decision-trail/{_Seeded.gapped_order_id}")
    assert res.status_code == 200, res.text
    trail = res.json()

    assert trail["cycle_id"] == "cycle_gap"
    assert trail["complete"] is False
    # the two gaps are each named, not silently omitted
    assert set(trail["missing_links"]) == {"analysis_context", "trigger"}
    assert trail["analysis_context"] is None
    assert trail["trigger"] is None

    # the hops that DO exist are still linked
    assert trail["order"]["status"] == "SUBMITTED"
    assert trail["risk_approval"]["verdict"] == "APPROVE"
    assert trail["strategy_decision"]["action"] == "HEDGE"
    assert [h["strategy_type"] for h in trail["hypotheses"]] == ["PUT_SPREAD"]


def test_unknown_order_id_404s(client: TestClient) -> None:
    res = client.get("/decision-trail/999999")
    assert res.status_code == 404
    assert "999999" in res.json()["detail"]
