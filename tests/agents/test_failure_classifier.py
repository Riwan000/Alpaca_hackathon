"""Critical vs recoverable failure classification — task P6-BE-9 / issue #155 (BRD §31).

- an Alpaca auth error (missing / rejected credentials) → ``CRITICAL`` → the
  cycle halts and never reaches ``EXECUTION``;
- one news / enrichment source down → ``RECOVERABLE`` → degrade the context,
  note the limitation, carry on;
- a failure inside the risk gate or the execution leg → ``CRITICAL`` regardless
  of the exception type ("risk engine unavailable" / "invalid execution state");
- an unclassifiable failure with no stage → ``CRITICAL`` (fail safe).
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.agents.base import AgentError
from backend.agents.context_builder import AnalysisInputs
from backend.agents.orchestrator.nodes import (
    OrchestratorDeps,
    analyzing_node,
    risk_check_node,
    route_after_analyzing,
    strategy_evaluation_node,
)
from backend.agents.orchestrator.resilience import (
    CriticalFailure,
    FailureClass,
    RecoverableFailure,
    RetriesExhausted,
    classify_failure,
)
from backend.integrations.alpaca.client import AlpacaCredentialsError, AlpacaError
from backend.models.enums import WorkflowNode

pytestmark = pytest.mark.unit


class TestClassifyFailure:
    def test_alpaca_credentials_error_is_critical(self) -> None:
        assert classify_failure(AlpacaCredentialsError("no key")) is FailureClass.CRITICAL

    def test_alpaca_auth_status_is_critical_even_in_the_analysis_stage(self) -> None:
        exc = AlpacaError("Alpaca GET /v2/account -> 403: forbidden")
        assert classify_failure(exc, stage=WorkflowNode.ANALYZING) is FailureClass.CRITICAL

    def test_a_single_analysis_agent_down_is_recoverable(self) -> None:
        exc = AgentError("news source unavailable")
        assert classify_failure(exc, stage="ANALYZING") is FailureClass.RECOVERABLE

    def test_a_venue_5xx_in_the_risk_stage_is_critical(self) -> None:
        exc = AlpacaError("Alpaca POST /v2/orders -> 503: service unavailable")
        assert classify_failure(exc, stage=WorkflowNode.RISK_CHECK) is FailureClass.CRITICAL

    def test_execution_stage_failure_is_critical(self) -> None:
        assert classify_failure(RuntimeError("weird"), stage="EXECUTION") is FailureClass.CRITICAL

    def test_explicit_markers_win(self) -> None:
        assert classify_failure(CriticalFailure("x"), stage="ANALYZING") is FailureClass.CRITICAL
        assert classify_failure(RecoverableFailure("x"), stage="EXECUTION") is FailureClass.RECOVERABLE

    def test_unknown_with_no_stage_fails_safe_to_critical(self) -> None:
        assert classify_failure(RuntimeError("mystery")) is FailureClass.CRITICAL

    def test_retries_exhausted_is_classified_by_its_cause(self) -> None:
        wrapped = RetriesExhausted(AlpacaCredentialsError("gone"), attempts=3)
        assert classify_failure(wrapped, stage="ANALYZING") is FailureClass.CRITICAL


def test_pulling_alpaca_creds_mid_run_halts_before_execution(analysis_inputs) -> None:
    """The confirm step: an Alpaca auth failure while assembling context halts the
    cycle — ``ANALYZING`` routes straight to ``MONITORING``, never to strategy /
    risk / execution."""

    def _no_creds(_cycle_id: str | None) -> AnalysisInputs:
        raise AlpacaCredentialsError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set to use the Alpaca client"
        )

    out = analyzing_node(OrchestratorDeps(inputs_provider=_no_creds))({"cycle_id": "cyc-halt"})

    assert out["halted"] is True
    assert out["failure_class"] == "CRITICAL"
    assert out["route"] == "MONITORING"
    assert "hedge_context" not in out
    assert route_after_analyzing({"cycle_id": "cyc-halt", **out}) == "MONITORING"


def test_one_news_source_down_degrades_but_does_not_halt(mock_llm, analysis_inputs) -> None:
    """A recoverable analysis failure keeps the cycle going with a degraded context."""
    from backend.agents.assembler import ANALYSIS_AGENT_FNS

    def _news_down(*_a: Any, **_k: Any) -> Any:
        raise AgentError("news feed provider timed out")

    out = analyzing_node(
        OrchestratorDeps(
            inputs_provider=analysis_inputs,
            llm_client=mock_llm,
            agent_fns={**ANALYSIS_AGENT_FNS, "news": _news_down},
        )
    )({"cycle_id": "cyc-degrade"})

    assert out.get("halted") in (None, False)
    assert out["degraded"] is True
    assert out["hedge_context"].degraded_sections == ["news_context"]
    assert route_after_analyzing({"cycle_id": "cyc-degrade", **out}) == "STRATEGY_EVALUATION"


def test_risk_gate_failure_is_critical_and_halts(golden_hedge_context) -> None:
    """A raised failure inside the risk gate halts the cycle — BRD §31 lists
    "risk engine unavailable" as critical. Here the risk-checks store is missing
    its table, so ``RiskCheckRepository`` construction blows up inside the node."""
    import json

    from sqlalchemy import create_engine

    from tests.conftest import FakeLLMClient

    strat_llm = FakeLLMClient()
    strat_llm.response_content = json.dumps(
        {"decision": "SELECT_STRATEGY", "selected_strategy": "PROTECTIVE_PUT",
         "rationale": "protection", "confidence": 0.9}
    )
    base = {"cycle_id": golden_hedge_context.cycle_id, "hedge_context": golden_hedge_context}
    state = {**base, **strategy_evaluation_node(OrchestratorDeps(llm_client=strat_llm))(base)}

    unmigrated = create_engine("sqlite://", future=True)  # no tables at all
    out = risk_check_node(OrchestratorDeps(engine=unmigrated))(state)

    assert out["halted"] is True
    assert out["failure_class"] == "CRITICAL"
    assert out["route"] == "MONITORING"
    assert "risk_decision" not in out
