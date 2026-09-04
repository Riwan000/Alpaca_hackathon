"""End-to-end adaptive rebalancing — task P7-BE-10 / issue #178.

Test task for P7-BE-4 (cooldown) / P7-BE-6 (reassessment outcomes) / P7-BE-7
(apply-change). Scripts the BRD §37 Scene 8 story:

    vol spike  → reassessment says INCREASE (add protection)
    vol falls  → reassessment says DECREASE → a real (paper) order reduces the
                 hedge, hands-off, and a signed ``hedge_changes`` row is written

and, separately, the cooldown contract: a normal trigger inside the
post-adjustment window is suppressed, an emergency trigger bypasses it.
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.agents.monitoring.reassessment import should_escalate
from backend.agents.orchestrator.nodes import OrchestratorDeps, monitoring_node
from backend.db.monitoring_repo import (
    MonitoringRepository,
    MonitoringStateRecord,
)
from backend.db.orders_repo import OrderRepository
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType, TriggerType
from backend.models.hedge_context import (
    CurrentHedge,
    HedgeContext,
    HedgeObjective,
    MarketState,
    PortfolioState,
)
from backend.models.monitoring import MonitoringState, TriggerObservation

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Iterator[Engine]:
    """A scratch SQLite database migrated to head, disposed on teardown."""
    from backend.db import OVERRIDE_ENV_VAR, normalize_driver

    db_url = f"sqlite:///{tmp_path / 'adaptation.db'}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed:\n{proc.stdout}\n{proc.stderr}"
    engine = create_engine(normalize_driver(db_url), future=True)
    try:
        yield engine
    finally:
        engine.dispose()


class _FillingBroker:
    """Echoes any submitted payload back as fully filled."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def submit_order(self, payload: dict) -> dict:
        self.payloads.append(payload)
        if "legs" in payload:
            base = int(payload["qty"])
            return {
                "id": "adapt-combo-1",
                "status": "filled",
                "submitted_at": "2026-09-04T15:00:00Z",
                "filled_at": "2026-09-04T15:00:02Z",
                "legs": [
                    {
                        "symbol": leg["symbol"],
                        "side": leg["side"],
                        "qty": str(int(leg["ratio_qty"]) * base),
                        "filled_qty": str(int(leg["ratio_qty"]) * base),
                        "filled_avg_price": "2.10",
                        "status": "filled",
                        "filled_at": "2026-09-04T15:00:01Z",
                    }
                    for leg in payload["legs"]
                ],
            }
        return {
            "id": "adapt-single-1",
            "symbol": payload["symbol"],
            "side": payload["side"],
            "qty": payload["qty"],
            "filled_qty": payload["qty"],
            "filled_avg_price": "2.10",
            "status": "filled",
            "submitted_at": "2026-09-04T15:00:00Z",
            "filled_at": "2026-09-04T15:00:02Z",
        }


def _ctx(*, hedge_ratio: float, target: float, volatility: float, drawdown: float, vix: float) -> HedgeContext:
    now = _dt.datetime.now(_dt.timezone.utc)
    exp = (now + _dt.timedelta(days=30)).date()
    return HedgeContext(
        cycle_id="cyc-adapt",
        timestamp=now,
        objective=HedgeObjective(
            max_hedge_budget_pct=0.05, drawdown_tolerance_pct=0.10, target_hedge_ratio=target
        ),
        portfolio_state=PortfolioState(
            total_value=250_000.0, cash=100_000.0, equity=150_000.0, buying_power=120_000.0,
            drawdown=drawdown, volatility=volatility, beta=1.0, gross_exposure=0.6,
        ),
        market_state=MarketState(regime="LOW_VOL", vix=vix, index_trend="UP"),
        current_hedge=CurrentHedge(
            active=True,
            strategy_type=StrategyType.PROTECTIVE_PUT,
            hedge_ratio=hedge_ratio,
            target_hedge_ratio=target,
            expiration=exp,
            hedge_pnl=140.0,
            legs=[
                OptionLeg(
                    underlying="AAPL", right=OptionRight.PUT, side=OrderSide.BUY,
                    strike=150.0, expiration=exp, quantity=4,
                )
            ],
        ),
    )


_SPIKE_CTX = _ctx(hedge_ratio=0.80, target=0.80, volatility=0.36, drawdown=-0.09, vix=33.0)
_STABILIZED_CTX = _ctx(hedge_ratio=0.80, target=0.40, volatility=0.16, drawdown=-0.012, vix=15.0)
_MILD_DRIFT_CTX = _ctx(hedge_ratio=0.80, target=0.55, volatility=0.12, drawdown=-0.004, vix=13.0)
# A catastrophic breach (>= MonitoringThresholds.emergency_drawdown, 15%) — the
# only shape evaluate_emergency() marks is_emergency=True, so it is the only
# shape that may bypass a cooldown (P7-BE-4).
_EMERGENCY_CTX = _ctx(hedge_ratio=0.80, target=0.80, volatility=0.30, drawdown=-0.22, vix=28.0)


def _deps(engine, broker=None) -> OrchestratorDeps:
    # no llm_client -> the ReassessmentAgent uses its deterministic heuristic
    return OrchestratorDeps(engine=engine, broker=broker)


# --------------------------------------------------------------------------- #
# the scripted stabilization story
# --------------------------------------------------------------------------- #


def test_vol_spike_reassessment_recommends_increasing_protection(migrated_engine) -> None:
    node = monitoring_node(_deps(migrated_engine))

    out = node({"cycle_id": "cyc-adapt", "hedge_context": _SPIKE_CTX})

    assert TriggerType.DRAWDOWN_LIMIT in out["monitoring_state"].active_triggers
    assert out["reassessment_decision"].outcome is HedgeAction.INCREASE
    # INCREASE is a re-hedge, not a position-reducing change — nothing is closed
    assert MonitoringRepository(migrated_engine).list_hedge_changes("cyc-adapt") == []


def test_stabilization_script_reduces_the_hedge_hands_off(migrated_engine) -> None:
    """Confirm — the end-to-end stabilization script reduces the hedge without
    human input."""
    broker = _FillingBroker()
    node = monitoring_node(_deps(migrated_engine, broker))

    out = node({"cycle_id": "cyc-adapt", "hedge_context": _STABILIZED_CTX})

    decision = out["reassessment_decision"]
    assert decision.outcome in {HedgeAction.DECREASE, HedgeAction.REMOVE}
    summary = out["reassessment_result"]
    assert summary["changed_position"] is True
    assert summary["cleared_risk_gate"] is True

    repo = MonitoringRepository(migrated_engine)
    changes = repo.list_hedge_changes("cyc-adapt")
    assert len(changes) == 1
    assert float(changes[0].delta) < 0
    assert float(changes[0].after_hedge_ratio) < float(changes[0].before_hedge_ratio)

    # a real paper order was placed, hands-off, to reduce the hedge
    assert broker.payloads
    assert OrderRepository(migrated_engine).list_for_cycle("cyc-adapt")

    # reassessment_events links the trigger to the outcome
    reassessments = repo.list_reassessments("cyc-adapt")
    assert len(reassessments) == 1
    assert str(reassessments[0].outcome) in {"DECREASE", "REMOVE"}


# --------------------------------------------------------------------------- #
# cooldown contract — normal suppressed, emergency bypasses
# --------------------------------------------------------------------------- #


def _state_with_cooldown(
    trigger_type: TriggerType, *, minutes_left: int, is_emergency: bool = False
) -> MonitoringState:
    now = _dt.datetime.now(_dt.timezone.utc)
    return MonitoringState(
        cycle_id="cyc-cooldown",
        as_of=now,
        active_triggers=[trigger_type],
        trigger_history=[
            TriggerObservation(
                trigger_type=trigger_type,
                observed_at=now,
                detail=trigger_type.value,
                is_emergency=is_emergency,
            )
        ],
        cooldown_until=now + _dt.timedelta(minutes=minutes_left),
        in_cooldown=True,
        reassessment_recommended=True,
    )


def test_normal_trigger_is_suppressed_inside_cooldown() -> None:
    esc = should_escalate(_state_with_cooldown(TriggerType.PORTFOLIO_DELTA, minutes_left=20))
    assert esc.escalate is False
    assert "cooldown" in esc.reason


def test_emergency_trigger_bypasses_cooldown() -> None:
    """Only ``evaluate_emergency``'s catastrophic breach (is_emergency=True) may
    bypass the cooldown — a plain DRAWDOWN_LIMIT breach does not (P7-BE-4)."""
    esc = should_escalate(
        _state_with_cooldown(TriggerType.DRAWDOWN_LIMIT, minutes_left=20, is_emergency=True)
    )
    assert esc.escalate is True
    assert esc.emergency is True
    assert esc.bypassed_cooldown is True


def test_cooldown_contract_end_to_end_through_the_node(migrated_engine) -> None:
    repo = MonitoringRepository(migrated_engine)
    future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=30)
    # a prior adjustment left a cooldown window in force
    repo.save_state(
        MonitoringStateRecord(
            cycle_id="cyc-adapt",
            current_hedge=__import__("decimal").Decimal("0.40"),
            target_hedge=__import__("decimal").Decimal("0.40"),
            cooldown_until=future,
        )
    )
    node = monitoring_node(_deps(migrated_engine, _FillingBroker()))

    # a normal drift trigger inside the window → suppressed
    mild = node({"cycle_id": "cyc-adapt", "hedge_context": _MILD_DRIFT_CTX})
    assert "reassessment_decision" not in mild
    assert any("cooldown" in n for n in mild.get("notes", []))

    # an emergency (hard drawdown) trigger inside the same window → bypasses it
    emergency = node({"cycle_id": "cyc-adapt", "hedge_context": _EMERGENCY_CTX})
    assert "reassessment_decision" in emergency
    assert emergency["reassessment_result"]["bypassed_cooldown"] is True
