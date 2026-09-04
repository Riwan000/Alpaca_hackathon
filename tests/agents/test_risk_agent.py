"""Risk Agent tests — tasks P5-BE-8 / P5-BE-9 (BRD §19–20).

* a deterministically-failed plan is ``REJECT`` even when the (stubbed) LLM says
  ``APPROVE`` — the LLM cannot override a hard fail and is not even consulted;
* the LLM cannot change or invent the strategy family;
* ``APPROVE`` / ``MODIFY`` / ``REJECT`` verdicts on a clean plan are honoured,
  with the :class:`RiskDecision` verdict invariants kept;
* ``test_persist`` — the decision validates as a ``RiskDecision`` and lands as
  exactly one ``risk_checks`` row.

The synthetic context carries an ``AAPL PUT 145`` option candidate and ample
buying power so that a plain ``_hypothesis()`` clears all eleven P5-BE-1..6
deterministic checks; individual tests then break one thing at a time.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.agents.risk import RiskAgent
from backend.agents.risk.engine import RiskEngineLimits
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.risk_checks_repo import RiskCheckRepository
from backend.models.common import OptionLeg
from backend.models.enums import (
    HedgeAction,
    OptionRight,
    OrderSide,
    RiskVerdict,
    StrategyType,
)
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskDecision
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

_NOW = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
_EXPIRY = date(2026, 10, 3)
_CYCLE = "cyc-p5-be-8"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

_CHECK_NAMES = [
    "hedge_budget",
    "max_hedge_ratio",
    "max_notional",
    "position_limit",
    "buying_power",
    "liquidity",
    "contract_validity",
    "expiration_window",
    "net_delta_bounds",
    "multileg_consistency",
    "price_band",
]


def _context(
    *,
    total_value: float = 100_000.0,
    buying_power: float = 60_000.0,
    aapl_shares: float = 100.0,
    with_candidate: bool = True,
    cycle_id: str = _CYCLE,
) -> HedgeContext:
    positions = []
    if aapl_shares:
        positions.append(
            {
                "symbol": "AAPL",
                "qty": aapl_shares,
                "avg_price": 150.0,
                "market_value": aapl_shares * 150.0,
                "asset_class": "EQUITY",
                "side": "BUY",
            }
        )
    candidates = []
    if with_candidate:
        candidates.append(
            {
                "underlying": "AAPL",
                "right": "PUT",
                "strike": 145.0,
                "expiration": _EXPIRY.isoformat(),
                "premium": 3.15,
                "bid": 3.1,
                "ask": 3.2,
                "open_interest": 4200,
                "volume": 900,
                "delta": -0.35,
                "iv": 0.3,
                "liquidity": "high",
            }
        )
    return HedgeContext.model_validate(
        {
            "cycle_id": cycle_id,
            "timestamp": _NOW.isoformat(),
            "portfolio_state": {
                "total_value": total_value,
                "cash": total_value / 2,
                "equity": total_value / 2,
                "buying_power": buying_power,
                "positions": positions,
            },
            "objective": {
                "max_hedge_budget_pct": 0.05,
                "drawdown_tolerance_pct": 0.10,
            },
            "option_candidates": candidates,
        }
    )


def _leg(
    *,
    strike: float = 145.0,
    quantity: int = 1,
    side: OrderSide = OrderSide.BUY,
    right: OptionRight = OptionRight.PUT,
) -> OptionLeg:
    return OptionLeg(
        underlying="AAPL",
        right=right,
        side=side,
        strike=strike,
        expiration=_EXPIRY,
        quantity=quantity,
    )


def _hypothesis(
    *,
    hedge_ratio: float | None = 0.5,
    cost: float = 250.0,
    legs: tuple[OptionLeg, ...] = (_leg(),),
    strategy: StrategyType = StrategyType.PROTECTIVE_PUT,
    cycle_id: str = _CYCLE,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        cycle_id=cycle_id,
        strategy=strategy,
        action=HedgeAction.NEW_HEDGE,
        viable=True,
        legs=list(legs),
        cost=cost,
        hedge_metrics=HedgeMetrics(hedge_ratio=hedge_ratio),
        rationale="synthetic hypothesis for the risk-agent tests",
    )


def _llm(
    *,
    verdict: str = "APPROVE",
    rationale: str = "No qualitative concern beyond the checklist.",
    modifications: list | None = None,
    violations: list | None = None,
    warnings: list | None = None,
    extra: dict | None = None,
) -> str:
    body = {
        "verdict": verdict,
        "rationale": rationale,
        "modifications": modifications or [],
        "violations": violations or [],
        "warnings": warnings or [],
    }
    if extra:
        body.update(extra)
    return json.dumps(body)


# --------------------------------------------------------------------------- #
# clean plan — LLM verdict is honoured
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_clean_plan_with_llm_approve_is_approved(mock_llm) -> None:
    mock_llm.response_content = _llm(verdict="APPROVE")

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert isinstance(decision, RiskDecision)
    assert decision.verdict is RiskVerdict.APPROVE
    assert decision.violations == []
    assert decision.approved_hypothesis is not None
    assert decision.approved_hypothesis.strategy is StrategyType.PROTECTIVE_PUT
    assert [c.name for c in decision.checks] == _CHECK_NAMES
    RiskDecision.model_validate(decision.model_dump())


# --------------------------------------------------------------------------- #
# a deterministic fail beats an LLM approve (P5-BE-8 confirm)
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_deterministic_fail_forces_reject_even_when_llm_approves(mock_llm) -> None:
    mock_llm.response_content = _llm(verdict="APPROVE", rationale="looks fine to me")

    # budget = 5_000; a 40_000 debit is a hard fail.
    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(cost=40_000.0), _context()
    )

    assert decision.verdict is RiskVerdict.REJECT
    assert decision.violations  # >= 1
    assert decision.approved_hypothesis is None
    assert "cannot override" in decision.rationale
    # the LLM was never consulted — a hard fail short-circuits the gate
    assert mock_llm.calls == []
    RiskDecision.model_validate(decision.model_dump())


@pytest.mark.unit
def test_an_unknown_contract_leg_is_a_deterministic_reject(mock_llm) -> None:
    mock_llm.response_content = _llm(verdict="APPROVE")

    # a 130 strike matches no candidate in the context → contract_validity fails
    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(legs=(_leg(strike=130.0),)), _context()
    )

    assert decision.verdict is RiskVerdict.REJECT
    assert mock_llm.calls == []


@pytest.mark.unit
def test_limits_override_can_turn_a_clean_plan_into_a_reject(mock_llm) -> None:
    mock_llm.response_content = _llm(verdict="APPROVE")
    tight = RiskEngineLimits(
        hedge_budget=10.0, max_hedge_ratio=1.0, max_notional=1e12
    )

    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(cost=250.0), _context(), limits=tight
    )

    assert decision.verdict is RiskVerdict.REJECT
    assert mock_llm.calls == []


# --------------------------------------------------------------------------- #
# the LLM cannot change / invent the strategy family
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_llm_cannot_change_the_strategy_family(mock_llm) -> None:
    mock_llm.response_content = _llm(
        verdict="APPROVE",
        extra={
            "strategy": "COLLAR",
            "selected_strategy": "COLLAR",
            "strategy_type": "COLLAR",
        },
    )

    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(strategy=StrategyType.PROTECTIVE_PUT), _context()
    )

    assert decision.verdict is RiskVerdict.APPROVE
    assert decision.approved_hypothesis.strategy is StrategyType.PROTECTIVE_PUT


@pytest.mark.unit
def test_a_modification_that_swaps_strategy_is_dropped(mock_llm) -> None:
    mock_llm.response_content = _llm(
        verdict="MODIFY",
        modifications=[
            {"field": "strategy_type", "to_value": "COLLAR", "reason": "prefer a collar"},
            {"field": "cost", "from_value": 250, "to_value": 180, "reason": "trim to mid"},
        ],
    )

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert decision.verdict is RiskVerdict.MODIFY
    assert [m.field for m in decision.modifications] == ["cost"]
    assert decision.approved_hypothesis.strategy is StrategyType.PROTECTIVE_PUT


# --------------------------------------------------------------------------- #
# MODIFY / REJECT on a deterministically-clean plan
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_llm_modify_with_a_concrete_adjustment_is_honoured(mock_llm) -> None:
    mock_llm.response_content = _llm(
        verdict="MODIFY",
        modifications=[
            {"field": "contracts", "from_value": 2, "to_value": 1, "reason": "halve the size"}
        ],
        warnings=["front-month IV is elevated"],
    )

    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(legs=(_leg(quantity=1),)), _context()
    )

    assert decision.verdict is RiskVerdict.MODIFY
    assert len(decision.modifications) == 1
    assert decision.modifications[0].to_value == 1
    assert "front-month IV is elevated" in decision.warnings
    RiskDecision.model_validate(decision.model_dump())


@pytest.mark.unit
def test_llm_modify_without_a_modification_falls_back_to_approve(mock_llm) -> None:
    mock_llm.response_content = _llm(verdict="MODIFY", modifications=[])

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert decision.verdict is RiskVerdict.APPROVE  # cannot MODIFY nothing
    assert decision.modifications == []


@pytest.mark.unit
def test_llm_reject_is_forwarded_with_its_violation(mock_llm) -> None:
    mock_llm.response_content = _llm(
        verdict="REJECT",
        violations=["earnings land inside the option's life"],
        rationale="event risk the checklist does not model",
    )

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert decision.verdict is RiskVerdict.REJECT
    assert "earnings land inside the option's life" in decision.violations
    assert decision.approved_hypothesis is None


@pytest.mark.unit
def test_llm_reject_without_a_violation_still_names_one(mock_llm) -> None:
    mock_llm.response_content = _llm(
        verdict="REJECT",
        violations=[],
        rationale="premium is too rich versus the protection bought",
    )

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert decision.verdict is RiskVerdict.REJECT
    assert decision.violations == ["premium is too rich versus the protection bought"]
    RiskDecision.model_validate(decision.model_dump())  # validator needs >= 1 violation


# --------------------------------------------------------------------------- #
# LLM unavailable → deterministic APPROVE (the hard checks already cleared)
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_unparsable_llm_response_falls_back_to_deterministic_approve(mock_llm) -> None:
    mock_llm.response_content = "sorry, I can't help with that"

    decision = RiskAgent(client=mock_llm).review(_hypothesis(), _context())

    assert decision.verdict is RiskVerdict.APPROVE
    assert "deterministic" in decision.rationale.lower()
    assert decision.approved_hypothesis is not None


# --------------------------------------------------------------------------- #
# persistence (P5-BE-9)
# --------------------------------------------------------------------------- #


def _scratch_url(tmp_path: Path) -> str:
    return (
        os.environ.get("TEST_DATABASE_URL")
        or f"sqlite:///{tmp_path / 'risk_agent_scratch.db'}"
    )


@pytest.fixture
def risk_repo(tmp_path: Path):
    db_url = _scratch_url(tmp_path)
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        yield RiskCheckRepository(engine)
    finally:
        engine.dispose()


@pytest.mark.integration
def test_persist(mock_llm, risk_repo: RiskCheckRepository) -> None:
    """P5-BE-9: the decision validates as ``RiskDecision`` and lands as one row."""
    mock_llm.response_content = _llm(
        verdict="APPROVE", warnings=["thin open interest on the far leg"]
    )

    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(), _context(), repo=risk_repo
    )

    RiskDecision.model_validate(decision.model_dump())

    assert risk_repo.count() == 1
    row = risk_repo.for_cycle(_CYCLE)
    assert row is not None
    assert row.verdict == "APPROVE"
    assert row.violations is None
    assert "thin open interest on the far leg" in row.warnings
    assert row.checks and row.checks[0]["name"] == "hedge_budget"
    assert len(row.checks) == len(_CHECK_NAMES)

    # the P5-BE-9 confirm query
    with risk_repo._engine.connect() as conn:
        last = conn.execute(
            text("select cycle_id, verdict from risk_checks order by id desc limit 1")
        ).one()
    assert last[0] == _CYCLE
    assert last[1] == "APPROVE"


@pytest.mark.integration
def test_persist_a_deterministic_reject_row(
    mock_llm, risk_repo: RiskCheckRepository
) -> None:
    mock_llm.response_content = _llm(verdict="APPROVE")  # ignored on a hard fail

    decision = RiskAgent(client=mock_llm).review(
        _hypothesis(cost=40_000.0), _context(), repo=risk_repo
    )

    assert decision.verdict is RiskVerdict.REJECT
    row = risk_repo.for_cycle(_CYCLE)
    assert row is not None
    assert row.verdict == "REJECT"
    assert row.violations  # the repo refuses a REJECT with no violation
