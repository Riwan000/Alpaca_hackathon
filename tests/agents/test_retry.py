"""Per-node retry with bounded backoff — task P6-BE-8 / issue #154.

- a transient failure is retried up to ``max_attempts`` with an exponential,
  capped backoff;
- injecting 2 transient failures → the call succeeds on attempt 3;
- a non-transient failure is *not* retried — it propagates immediately;
- when every attempt fails the loop stops (bounded, no spin) and raises
  ``RetriesExhausted`` carrying the cause, which the classifier can then judge.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.agents.context_builder import AnalysisInputs
from backend.agents.orchestrator.nodes import OrchestratorDeps, analyzing_node
from backend.agents.orchestrator.resilience import (
    RetriesExhausted,
    RetryPolicy,
    TransientError,
    classify_failure,
    run_with_retry,
)
from backend.models.hedge_context import HedgeContext

pytestmark = pytest.mark.unit


class _Clock:
    """Records every sleep instead of waiting."""

    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def test_succeeds_on_the_third_attempt_after_two_transient_failures() -> None:
    clock = _Clock()
    calls = {"n": 0}

    def _flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError(f"blip {calls['n']}")
        return "ok"

    out = run_with_retry(_flaky, policy=RetryPolicy(base_delay_s=0.5, backoff=2.0), sleep=clock)

    assert out == "ok"
    assert calls["n"] == 3
    assert clock.slept == [0.5, 1.0]  # backoff after attempts 1 and 2, none after the last


def test_backoff_is_capped_at_max_delay() -> None:
    clock = _Clock()

    def _always_transient() -> None:
        raise TransientError("nope")

    with pytest.raises(RetriesExhausted):
        run_with_retry(
            _always_transient,
            policy=RetryPolicy(max_attempts=5, base_delay_s=1.0, backoff=10.0, max_delay_s=20.0),
            sleep=clock,
        )

    assert clock.slept == [1.0, 10.0, 20.0, 20.0]  # 100 and 1000 both clamp to 20


def test_a_non_transient_failure_is_not_retried() -> None:
    clock = _Clock()
    calls = {"n": 0}

    def _hard() -> None:
        calls["n"] += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        run_with_retry(_hard, policy=RetryPolicy(), sleep=clock)

    assert calls["n"] == 1
    assert clock.slept == []


def test_exhaustion_is_bounded_and_raises_a_classifiable_cause() -> None:
    clock = _Clock()
    calls = {"n": 0}

    def _always() -> None:
        calls["n"] += 1
        raise TransientError("still down")

    with pytest.raises(RetriesExhausted) as excinfo:
        run_with_retry(_always, policy=RetryPolicy(max_attempts=3), sleep=clock)

    assert calls["n"] == 3  # bounded — not an infinite loop
    assert excinfo.value.attempts == 3
    assert isinstance(excinfo.value.cause, TransientError)
    # the classifier unwraps it (stage-driven: an analysis blip degrades, it does not halt)
    assert classify_failure(excinfo.value, stage="ANALYZING").value == "RECOVERABLE"


def test_analyzing_node_retries_its_inputs_fetch_then_succeeds(
    mock_llm, analysis_inputs
) -> None:
    clock = _Clock()
    calls = {"n": 0}

    def _flaky_provider(cycle_id: str | None) -> AnalysisInputs:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("inputs API 503")
        return analysis_inputs(cycle_id)

    node = analyzing_node(
        OrchestratorDeps(
            inputs_provider=_flaky_provider,
            llm_client=mock_llm,
            retry_policy=RetryPolicy(base_delay_s=0.1, backoff=2.0),
            sleep=clock,
        )
    )

    out = node({"cycle_id": "cyc-retry"})

    assert calls["n"] == 3
    assert clock.slept == [0.1, 0.2]
    assert isinstance(out["hedge_context"], HedgeContext)
    assert "errors" not in out and not out.get("halted")


def test_analyzing_node_degrades_when_retries_are_exhausted(mock_llm) -> None:
    clock = _Clock()

    def _down_provider(_cycle_id: str | None) -> AnalysisInputs:
        raise TransientError("inputs API down")

    node = analyzing_node(
        OrchestratorDeps(
            inputs_provider=_down_provider,
            llm_client=mock_llm,
            retry_policy=RetryPolicy(max_attempts=3, base_delay_s=0.01),
            sleep=clock,
        )
    )

    out = node({"cycle_id": "cyc-retry-exhausted"})

    assert len(clock.slept) == 2  # 3 attempts → 2 backoffs, then give up
    assert "hedge_context" not in out
    assert out["route"] == "MONITORING"
    assert out["failure_class"] == "RECOVERABLE"
    assert not out.get("halted")
    assert any("ANALYZING" in e for e in out["errors"])
