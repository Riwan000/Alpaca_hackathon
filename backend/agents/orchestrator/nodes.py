"""Real node bodies for the orchestrator graph — tasks P6-BE-2 … P6-BE-6.

The P6-BE-1 skeleton (:mod:`backend.agents.orchestrator.graph`) chains six
placeholder nodes in order. This module supplies the real ones — pass an
:class:`OrchestratorDeps` to :func:`build_state_graph` and each node runs its
phase and writes its contract onto the :class:`~backend.agents.orchestrator.graph.OrchestratorState`:

======================  ===================================  =============================
node                    wraps                                writes
======================  ===================================  =============================
``ANALYZING``           Phase 3 — :func:`assemble_hedge_context`  ``hedge_context`` (+ ``degraded``)
``STRATEGY_EVALUATION`` Phase 4 — 4 agents → prefilter → mgr  ``strategy_decision`` (+ ``route``)
``RISK_CHECK``          Phase 5 risk gate — :class:`RiskAgent`  ``risk_decision`` (+ ``route``)
``EXECUTION``           Phase 5 execution                    ``execution_result``
``MONITORING``          Phase 7 hand-off placeholder         ``monitoring_state`` (terminal)
======================  ===================================  =============================

``INITIAL`` stays a marker. Every dependency (LLM client, broker, DB
:class:`~sqlalchemy.engine.Engine`) lives on :class:`OrchestratorDeps`, never on
the graph state, so a later ``SqliteSaver`` only has to serialise the pydantic
payloads.

**Routing (P6-BE-7).** Each decision node writes a ``route`` hint and
:func:`route_after_analyzing` / :func:`route_after_strategy` /
:func:`route_after_risk` re-derive the same next node as pure functions;
:func:`~backend.agents.orchestrator.graph.build_state_graph` attaches them as
``add_conditional_edges`` when it is given ``deps``. ``RISK_CHECK`` and
``EXECUTION`` still self-guard as a belt-and-braces check — a ``NO_TRADE`` /
``REASSESS`` decision or a non-``APPROVE`` verdict never reaches the broker even
if a caller runs the linear (``deps``-free) skeleton.

**Retry & failure class (P6-BE-8 / P6-BE-9).** ``ANALYZING`` retries its live
inputs fetch with bounded backoff (:func:`~backend.agents.orchestrator.resilience.run_with_retry`)
before giving up. Any caught node failure is run through
:func:`~backend.agents.orchestrator.resilience.classify_failure`: ``CRITICAL``
(BRD §31 — broker auth, risk engine down, invalid execution state) sets
``halted`` and routes to ``MONITORING`` so nothing trades; ``RECOVERABLE`` (a
news / enrichment source down) degrades and carries on.

**Transition persistence (P6-BE-10).** :func:`build_nodes` wraps every body so
entering and leaving it writes a timestamped ``workflow_state`` row via a
:class:`~backend.agents.orchestrator.persistence.TransitionSink`.

**Persistence divergence from ``POST /execute``.** The ``risk_checks`` row is
written once, by ``RISK_CHECK`` (``RiskAgent.review(repo=...)``); ``EXECUTION``
deliberately skips step 2 of :mod:`backend.api.execute` so the row is not
double-written. ``EXECUTION`` also self-guards on its own persisted effect
(``OrderRepository.list_for_cycle``) so a graph re-invoke does not double an
order — the same obligation :mod:`backend.agents.orchestrator.runner` places on a
side-effecting node. The guard rests on this rule: **once ``submit_plan``
returns, an ``orders`` row is written unconditionally** — including for a
``FAILED`` result whose broker order could not be mapped — so the row is there
for the next invoke to find. A failure *before* ``submit_plan`` returns (bad
plan, pre-flight abort, no broker, a combo the broker rejected outright) writes
only an ``execution_failures`` row and stays retryable.

Known gap: a *legged fallback* (``constraints.allow_legging`` — set only by a
risk ``MODIFY``) that fills an early leg then raises on a later one leaves that
leg live with no ``orders`` row, because :func:`submit_plan` raises rather than
returning a partial outcome. This is inherited from ``submit_plan`` (``POST
/execute`` has the same exposure and no guard at all); the fix belongs there.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from backend.agents.assembler import assemble_hedge_context
from backend.agents.execution import (
    ExecutionPlanError,
    ExecutionResultError,
    build_execution_plan,
    build_execution_result,
    persist_execution_result,
    run_preflight,
)
from backend.agents.ingest import build_live_analysis_inputs
from backend.agents.risk.agent import RiskAgent
from backend.agents.strategies import (
    CollarAgent,
    NoHedgeAgent,
    ProtectivePutAgent,
    PutSpreadAgent,
    StrategyManager,
    prefilter,
)
from backend.agents.orchestrator.graph import OrchestratorState
from backend.agents.orchestrator.persistence import (
    TransitionSink,
    WorkflowTransitionSink,
    wrap_with_transition_hook,
)
from backend.agents.orchestrator.resilience import (
    FailureClass,
    RetryPolicy,
    classify_failure,
    is_transient,
    run_with_retry,
)
from backend.integrations.alpaca.client import AlpacaError
from backend.integrations.alpaca.orders import OrderSubmitter, SubmitOutcome, submit_plan
from backend.models.enums import (
    DecisionType,
    ExecutionStatus,
    RiskVerdict,
    WorkflowNode,
)
from backend.models.execution import ExecutionResult
from backend.models.hedge_context import HedgeContext
from backend.models.monitoring import MonitoringState

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

    from backend.agents.context_builder import AnalysisInputs

__all__ = [
    "OrchestratorDeps",
    "NodeBody",
    "build_nodes",
    "analyzing_node",
    "strategy_evaluation_node",
    "risk_check_node",
    "execution_node",
    "monitoring_node",
    "route_after_analyzing",
    "route_after_strategy",
    "route_after_risk",
]

logger = logging.getLogger(__name__)

#: A compiled node body: current state in, a partial state update out.
NodeBody = Callable[[OrchestratorState], "dict[str, Any]"]

#: Strategy outcomes that skip the risk gate and go straight toward MONITORING.
_SKIP_STRATEGY: frozenset[DecisionType] = frozenset(
    {DecisionType.NO_TRADE, DecisionType.REASSESS}
)
#: Risk verdicts that clear a plan for execution.
_EXECUTABLE_VERDICTS: frozenset[RiskVerdict] = frozenset(
    {RiskVerdict.APPROVE, RiskVerdict.MODIFY}
)

_MONITORING = WorkflowNode.MONITORING.value
_STRATEGY = WorkflowNode.STRATEGY_EVALUATION.value
_RISK_CHECK = WorkflowNode.RISK_CHECK.value
_EXECUTION = WorkflowNode.EXECUTION.value


# --------------------------------------------------------------------------- #
# dependencies
# --------------------------------------------------------------------------- #


@dataclass
class OrchestratorDeps:
    """Injectables the real nodes need — a test swaps in fakes.

    Every field is optional. With ``engine=None`` the nodes still run but persist
    nothing (``agent_runs`` / ``risk_checks`` / ``orders`` / ``monitoring_state``
    rows are skipped); with ``broker=None`` ``EXECUTION`` returns a truthful
    ``FAILED`` instead of sending an order. ``inputs_provider`` is called with the
    cycle id so the whole audit trail keys off one id.
    """

    inputs_provider: Callable[[str | None], "AnalysisInputs"] | None = None
    llm_client: Any | None = None
    broker: OrderSubmitter | None = None
    engine: "Engine | None" = None
    agent_fns: Mapping[str, Any] | None = None
    #: Re-validate the plan against the state's context the instant before submit
    #: (contract / price band / quote staleness). Mirrors ``ExecuteRequest.preflight``;
    #: turn it off only to replay a recorded cycle whose context is deliberately stale.
    preflight: bool = True
    #: P6-BE-8 — bounded retry with backoff around a node's external fetch
    #: (currently the ``inputs_provider`` in ``ANALYZING``). ``None`` uses the
    #: default policy (3 attempts, 0.5s base, ×2 backoff).
    retry_policy: RetryPolicy | None = None
    #: Injected so tests assert on the backoff schedule without waiting.
    sleep: Callable[[float], None] = time.sleep
    #: P6-BE-10 — where every node ENTER/EXIT is recorded. ``None`` + an ``engine``
    #: builds a :class:`WorkflowTransitionSink`; ``None`` + no engine disables the
    #: hook. ``persist_transitions=False`` disables it even with an engine.
    transition_sink: TransitionSink | None = None
    persist_transitions: bool = True


def _default_inputs_provider(_cycle_id: str | None) -> "AnalysisInputs":
    """Live inputs bundle — the cycle id is aligned by :func:`analyzing_node`."""
    return build_live_analysis_inputs()


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #


def _stamp(node: WorkflowNode, **payload: Any) -> dict[str, Any]:
    """A node's return value: the skeleton ``current_node`` / ``visited`` keys
    plus whatever contract / routing keys the node owns."""
    return {"current_node": node.value, "visited": [node.value], **payload}


def _context(state: OrchestratorState) -> HedgeContext | None:
    """The ``hedge_context`` from state, or ``None`` when ANALYZING never produced one."""
    ctx = state.get("hedge_context")
    return ctx if isinstance(ctx, HedgeContext) else None


def _decimal(value: float | None) -> Decimal:
    """A nullable ratio → a non-null ``Decimal`` (via ``str`` to dodge binary noise)."""
    return Decimal(str(value if value is not None else 0.0))


def _failure_payload(
    node: WorkflowNode, exc: BaseException, *, note: str | None = None
) -> dict[str, Any]:
    """A stamped payload for a caught node failure, classified per BRD §31 (P6-BE-9).

    Always routes to ``MONITORING`` and records an ``errors`` entry. A
    ``CRITICAL`` classification also sets ``halted`` / ``failure_class`` so the
    cycle stops before the broker and the persistence hook logs the exit as
    ``HALTED``; a ``RECOVERABLE`` one just carries the class for the audit trail.
    """
    cls = classify_failure(exc, stage=node)
    payload: dict[str, Any] = {
        "route": _MONITORING,
        "errors": [f"{node.value}: {type(exc).__name__}: {exc}"],
        "failure_class": cls.value,
    }
    if cls is FailureClass.CRITICAL:
        payload["halted"] = True
    if note:
        payload["notes"] = [note]
    return _stamp(node, **payload)


# --------------------------------------------------------------------------- #
# P6-BE-2 — ANALYZING
# --------------------------------------------------------------------------- #


def analyzing_node(deps: OrchestratorDeps) -> NodeBody:
    """Wrap the Phase 3 chain: build a :class:`HedgeContext` onto the state.

    A per-agent failure is already absorbed by
    :func:`assemble_hedge_context` — the section name lands in
    ``HedgeContext.degraded_sections`` and this node sets ``degraded=True``. Only a
    hard failure (the inputs provider or context builder raising) leaves no
    context: that is an ``errors`` entry + ``route=MONITORING``, never a crash.
    """
    provider = deps.inputs_provider or _default_inputs_provider
    policy = deps.retry_policy or RetryPolicy()
    if deps.engine is None:
        logger.warning("ANALYZING node built with engine=None; agent_runs will not persist")

    def _run(state: OrchestratorState) -> dict[str, Any]:
        cycle_id = state.get("cycle_id")
        run_repo = _agent_run_repo(deps.engine)
        try:
            # P6-BE-8 — a transient blip fetching live inputs is retried (bounded,
            # backing off) before the node falls back to degrade / halt.
            inputs = run_with_retry(
                lambda: provider(cycle_id),
                policy=policy,
                retry_on=is_transient,
                sleep=deps.sleep,
            )
            if cycle_id and inputs.cycle_id != cycle_id:
                inputs = inputs.model_copy(update={"cycle_id": cycle_id})
            ctx = assemble_hedge_context(
                inputs,
                client=deps.llm_client,
                agent_fns=deps.agent_fns,
                run_repo=run_repo,
            )
        except Exception as exc:  # noqa: BLE001 - a hard analysis failure degrades/halts the cycle, never crashes it
            logger.exception("ANALYZING node could not build a HedgeContext")
            return _failure_payload(WorkflowNode.ANALYZING, exc)

        payload: dict[str, Any] = {"hedge_context": ctx, "cycle_id": ctx.cycle_id}
        if ctx.degraded_sections:
            payload["degraded"] = True
            payload["notes"] = [
                f"ANALYZING: degraded sections — {', '.join(ctx.degraded_sections)}"
            ]
        return _stamp(WorkflowNode.ANALYZING, **payload)

    _run.__name__ = "analyzing_node"
    return _run


def _agent_run_repo(engine: "Engine | None") -> Any | None:
    if engine is None:
        return None
    from backend.db.agent_runs_repo import AgentRunRepository

    return AgentRunRepository(engine)


# --------------------------------------------------------------------------- #
# P6-BE-3 — STRATEGY_EVALUATION
# --------------------------------------------------------------------------- #

_STRATEGY_AGENTS = (ProtectivePutAgent, PutSpreadAgent, CollarAgent, NoHedgeAgent)


def strategy_evaluation_node(deps: OrchestratorDeps) -> NodeBody:
    """Wrap Phase 4: four hedge-family agents → pre-filter → Strategy Manager.

    Consumes ``hedge_context``; writes ``strategy_decision``. ``route`` is
    ``MONITORING`` for a ``NO_TRADE`` / ``REASSESS`` outcome (nothing to risk-check)
    and ``RISK_CHECK`` otherwise.
    """

    def _run(state: OrchestratorState) -> dict[str, Any]:
        ctx = _context(state)
        if ctx is None:
            return _stamp(
                WorkflowNode.STRATEGY_EVALUATION,
                route=_MONITORING,
                errors=["STRATEGY_EVALUATION: no HedgeContext in state; cannot evaluate"],
            )
        try:
            hypotheses = [agent().propose(ctx) for agent in _STRATEGY_AGENTS]
            pre = prefilter(hypotheses, ctx)
            decision = StrategyManager(client=deps.llm_client).run(pre, ctx)
            _persist_strategy(deps.engine, hypotheses, decision)
        except Exception as exc:  # noqa: BLE001 - a strategy-layer failure routes to MONITORING, never crashes
            logger.exception("STRATEGY_EVALUATION node failed")
            return _failure_payload(WorkflowNode.STRATEGY_EVALUATION, exc)

        skip = decision.decision in _SKIP_STRATEGY
        payload: dict[str, Any] = {
            "strategy_decision": decision,
            "route": _MONITORING if skip else _RISK_CHECK,
        }
        if skip:
            payload["notes"] = [
                f"STRATEGY_EVALUATION: {decision.decision.value} → skipping to MONITORING"
            ]
        return _stamp(WorkflowNode.STRATEGY_EVALUATION, **payload)

    _run.__name__ = "strategy_evaluation_node"
    return _run


def _persist_strategy(
    engine: "Engine | None",
    hypotheses: list[Any],
    decision: Any,
) -> None:
    """Best-effort persistence of strategy hypotheses + decision."""
    if engine is None:
        return
    try:
        from backend.db.strategy_repo import (
            StrategyDecisionRecord,
            StrategyDecisionRepository,
            StrategyHypothesisRecord,
            StrategyHypothesisRepository,
        )

        hypo_repo = StrategyHypothesisRepository(engine)
        dec_repo = StrategyDecisionRepository(engine)

        records = []
        for hyp in hypotheses:
            verdict = "ACCEPTED" if getattr(hyp, "viable", True) else "REJECTED"
            legs = [leg.model_dump(mode="json") for leg in hyp.legs] if getattr(hyp, "legs", None) else None
            metrics: dict[str, Any] = {}
            m = getattr(hyp, "hedge_metrics", None)
            if m:
                if getattr(m, "cost_pct_of_portfolio", None) is not None:
                    metrics["cost_pct_of_portfolio"] = m.cost_pct_of_portfolio
                if getattr(m, "downside_protection_pct", None) is not None:
                    metrics["downside_protection_pct"] = m.downside_protection_pct
                if getattr(m, "hedge_ratio", None) is not None:
                    metrics["hedge_ratio"] = m.hedge_ratio
            records.append(
                StrategyHypothesisRecord(
                    cycle_id=hyp.cycle_id,
                    strategy_type=getattr(getattr(hyp, "strategy", None), "value", str(getattr(hyp, "strategy", "UNKNOWN"))),
                    verdict=verdict,
                    legs=legs or None,
                    metrics=metrics or None,
                    rejection_reason=getattr(hyp, "rejection_reason", None),
                )
            )

        saved = hypo_repo.save_many(records)

        selected_id: int | None = None
        if getattr(decision, "selected_hypothesis", None) is not None:
            sel_strat = getattr(
                getattr(decision.selected_hypothesis, "strategy", None),
                "value",
                str(getattr(decision.selected_hypothesis, "strategy", "")),
            )
            for saved_rec in saved:
                if saved_rec.strategy_type == sel_strat:
                    selected_id = saved_rec.id
                    break

        alternatives = [
            {
                "strategy": getattr(getattr(h, "strategy", None), "value", str(getattr(h, "strategy", ""))),
                "viable": h.viable,
                "cost": getattr(h, "cost", 0.0),
                "rationale": getattr(h, "rationale", ""),
            }
            for h in getattr(decision, "alternatives", [])
        ]
        comparison = [
            {
                "strategy": getattr(getattr(row, "strategy", None), "value", str(getattr(row, "strategy", ""))),
                "cost": getattr(row, "cost", 0.0),
                "downside_protection_pct": getattr(row, "downside_protection_pct", 0.0),
                "upside_giveup_pct": getattr(row, "upside_giveup_pct", 0.0),
                "liquidity": getattr(row, "liquidity", "HIGH"),
                "complexity": getattr(row, "complexity", "LOW"),
                "estimated_drag_bps": getattr(row, "estimated_drag_bps", 0.0),
            }
            for row in getattr(decision, "comparison", [])
        ]

        action = (
            getattr(decision.decision, "value", str(decision.decision))
            if hasattr(decision, "decision")
            else "NO_TRADE"
        )

        dec_repo.create(
            StrategyDecisionRecord(
                cycle_id=decision.cycle_id,
                action=action,
                rationale=getattr(decision, "rationale", ""),
                selected_hypothesis_id=selected_id,
                alternatives=alternatives or None,
                comparison=comparison or None,
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception("STRATEGY_EVALUATION node: persistence error for %s", getattr(decision, "cycle_id", "unknown"))



# --------------------------------------------------------------------------- #
# P6-BE-4 — RISK_CHECK
# --------------------------------------------------------------------------- #


def risk_check_node(deps: OrchestratorDeps) -> NodeBody:
    """Wrap the Phase 5 risk gate: :class:`RiskAgent` reviews the selected hypothesis.

    A ``NO_TRADE`` / ``REASSESS`` strategy decision has no hypothesis to review —
    this node is then a routed no-op toward ``MONITORING``. Otherwise it writes
    ``risk_decision`` (and the single ``risk_checks`` row, when an engine is
    configured) and routes to ``EXECUTION`` only on ``APPROVE`` / ``MODIFY``.
    """
    if deps.engine is None:
        logger.warning("RISK_CHECK node built with engine=None; risk_checks will not persist")

    def _run(state: OrchestratorState) -> dict[str, Any]:
        ctx = _context(state)
        decision = state.get("strategy_decision")
        hypothesis = getattr(decision, "selected_hypothesis", None)
        if ctx is None or hypothesis is None:
            reason = (
                "no HedgeContext in state"
                if ctx is None
                else f"{getattr(decision, 'decision', None)} carries no hypothesis"
            )
            return _stamp(
                WorkflowNode.RISK_CHECK,
                route=_MONITORING,
                notes=[f"RISK_CHECK: {reason}; routing to MONITORING"],
            )

        try:
            risk_decision = RiskAgent(client=deps.llm_client).review(
                hypothesis, ctx, repo=_risk_repo(deps.engine)
            )
        except Exception as exc:  # noqa: BLE001 - a gate failure fails safe: no execution
            logger.exception("RISK_CHECK node failed")
            # A failure in the risk gate is CRITICAL per BRD §31 ("risk engine
            # unavailable" → do not trade): _failure_payload halts the cycle.
            return _failure_payload(WorkflowNode.RISK_CHECK, exc)

        clear = risk_decision.verdict in _EXECUTABLE_VERDICTS
        payload: dict[str, Any] = {
            "risk_decision": risk_decision,
            "route": _EXECUTION if clear else _MONITORING,
        }
        if not clear:
            payload["notes"] = [
                f"RISK_CHECK: {risk_decision.verdict.value} → execution skipped"
            ]
        return _stamp(WorkflowNode.RISK_CHECK, **payload)

    _run.__name__ = "risk_check_node"
    return _run


def _risk_repo(engine: "Engine | None") -> Any | None:
    if engine is None:
        return None
    from backend.db.risk_checks_repo import RiskCheckRepository

    return RiskCheckRepository(engine)


# --------------------------------------------------------------------------- #
# P6-BE-5 — EXECUTION
# --------------------------------------------------------------------------- #


def execution_node(deps: OrchestratorDeps) -> NodeBody:
    """Wrap Phase 5 execution: plan → pre-flight → combo submit → mapped result.

    Guards, in order: only an ``APPROVE`` / ``MODIFY`` decision with an approved
    hypothesis executes; an order already on file for the cycle is never
    re-submitted (idempotency on a re-invoke). Pre-flight (``deps.preflight``,
    on by default) re-checks the plan against the state's context and aborts
    before any order is sent. Every failure — a bad plan, a pre-flight abort, a
    broker rejection, no broker configured — is written to state as a ``FAILED``
    :class:`ExecutionResult` **and** an ``errors`` entry; nothing is swallowed and
    nothing is raised out of the node.

    Persistence splits on *when* the failure happened. Before the broker is
    touched → an ``execution_failures`` row only, and the cycle stays retryable.
    After ``submit_plan`` returns → the order is live, so an ``orders`` row is
    written unconditionally (a ``FAILED`` mapping lands as ``REJECTED`` with the
    broker id, plus an ``execution_failures`` audit row); the idempotency guard
    then sees it and a re-invoke submits nothing.
    """
    if deps.engine is None:
        logger.warning("EXECUTION node built with engine=None; orders/fills will not persist")

    def _run(state: OrchestratorState) -> dict[str, Any]:
        risk_decision = state.get("risk_decision")
        cycle_id = str(
            state.get("cycle_id") or getattr(risk_decision, "cycle_id", None) or "unknown"
        )

        if (
            risk_decision is None
            or risk_decision.verdict not in _EXECUTABLE_VERDICTS
            or risk_decision.approved_hypothesis is None
        ):
            verdict = getattr(getattr(risk_decision, "verdict", None), "value", "none")
            return _stamp(
                WorkflowNode.EXECUTION,
                notes=[f"EXECUTION: no approved decision (verdict={verdict}); nothing submitted"],
            )

        if _order_already_on_file(deps.engine, cycle_id):
            return _stamp(
                WorkflowNode.EXECUTION,
                notes=["EXECUTION: an order is already on file for this cycle; not re-submitting"],
            )

        try:
            plan = build_execution_plan(risk_decision, approval_id=f"risk-{risk_decision.cycle_id}")
        except ExecutionPlanError as exc:
            return _failed(cycle_id, f"plan build failed: {exc}", engine=deps.engine)

        ctx = _context(state)
        if deps.preflight and ctx is not None:
            pf = run_preflight(plan, ctx)
            if not pf.ok:
                # No order was sent — record the abort, stay retryable.
                return _failed(
                    plan.cycle_id,
                    f"pre-flight abort [{pf.code}]: {pf.reason}",
                    engine=deps.engine,
                )

        if deps.broker is None:
            return _failed(plan.cycle_id, "no broker configured for the EXECUTION node", engine=deps.engine)

        try:
            outcome = submit_plan(deps.broker, plan)
        except AlpacaError as exc:
            # The broker rejected the combo outright — nothing went live, so this
            # stays retryable. (A legged fallback that fills one leg then raises
            # is the known gap noted in the module docstring — submit_plan raises
            # instead of returning a partial outcome; the fix belongs there.)
            # BRD §31: a broker failure at the execution leg is CRITICAL — the
            # cycle halts (P6-BE-9), even though it stays retryable on the DB side.
            return _failed(
                plan.cycle_id, f"broker submit failed: {exc}", engine=deps.engine, exc=exc
            )

        # An order is now live at the broker. From here every path writes an
        # ``orders`` row so a re-invoke's idempotency guard finds it.
        broker_order = outcome.responses[0] if outcome.combo else _combine_legged(outcome)
        try:
            result = build_execution_result(plan, broker_order)
        except ExecutionResultError as exc:
            result = ExecutionResult(
                cycle_id=plan.cycle_id,
                status=ExecutionStatus.FAILED,
                order_ids=list(outcome.order_ids),
                broker_order_id=next(iter(outcome.order_ids), None),
                error=f"broker order not mappable to a terminal result: {exc}",
            )

        _persist_submitted_order(deps.engine, plan, result)
        payload: dict[str, Any] = {"execution_result": result}
        if result.status is ExecutionStatus.FAILED:
            payload["errors"] = [f"EXECUTION: {result.error}"]
        return _stamp(WorkflowNode.EXECUTION, **payload)

    _run.__name__ = "execution_node"
    return _run


def _failed(
    cycle_id: str,
    message: str,
    *,
    engine: "Engine | None" = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    """A stamped EXECUTION payload for a failure *before* any order was placed.

    Writes an ``execution_failures`` audit row (when an engine is given) but no
    ``orders`` row — the cycle stays retryable. When ``exc`` is supplied it is
    classified (P6-BE-9); a ``CRITICAL`` verdict also flags ``halted`` /
    ``failure_class`` so the persistence hook logs the exit as ``HALTED``.
    """
    _record_failure(engine, cycle_id, message)
    result = ExecutionResult(
        cycle_id=cycle_id, status=ExecutionStatus.FAILED, error=message
    )
    payload: dict[str, Any] = {
        "execution_result": result,
        "errors": [f"EXECUTION: {message}"],
    }
    if exc is not None:
        cls = classify_failure(exc, stage=WorkflowNode.EXECUTION)
        payload["failure_class"] = cls.value
        if cls is FailureClass.CRITICAL:
            payload["halted"] = True
    return _stamp(WorkflowNode.EXECUTION, **payload)


def _order_already_on_file(engine: "Engine | None", cycle_id: str) -> bool:
    if engine is None:
        return False
    try:
        from backend.db.orders_repo import OrderRepository

        return bool(OrderRepository(engine).list_for_cycle(cycle_id))
    except Exception:  # noqa: BLE001 - the guard must never be the thing that breaks the node
        logger.exception("EXECUTION node: order-on-file check failed for %s", cycle_id)
        return False


def _record_failure(
    engine: "Engine | None", cycle_id: str, reason: str | None
) -> None:
    """Write one ``execution_failures`` audit row. Best effort."""
    if engine is None:
        return
    try:
        from backend.db.execution_failures_repo import (
            ExecutionFailureRecord,
            ExecutionFailureRepository,
        )

        ExecutionFailureRepository(engine).create(
            ExecutionFailureRecord(
                cycle_id=cycle_id, stage="EXECUTION", reason=reason or "unknown"
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception("EXECUTION node: execution_failures write failed for %s", cycle_id)


def _persist_submitted_order(
    engine: "Engine | None", plan: Any, result: ExecutionResult
) -> None:
    """Persist the ``orders`` row (+ fills) for an order the broker accepted.

    Called only *after* ``submit_plan`` returns, so the row is written for every
    ``result.status`` — a ``FAILED`` mapping lands as ``REJECTED`` and also gets
    an ``execution_failures`` audit row. Best effort: a persistence error is
    logged, never raised, so it cannot mask the result on the state.
    """
    if engine is None:
        return
    try:
        persist_execution_result(engine, plan, result)
    except Exception:  # noqa: BLE001
        logger.exception("EXECUTION node: orders/fills persistence failed for %s", plan.cycle_id)
    if result.status is ExecutionStatus.FAILED:
        _record_failure(engine, plan.cycle_id, result.error)


def _combine_legged(outcome: SubmitOutcome) -> dict[str, Any]:
    """Fold independent single-leg responses into one combo-shaped order object.

    Mirrors :func:`backend.api.execute._combine_legged` — the legged fallback
    only fires when the broker rejects a combo as unsupported.
    """
    legs = list(outcome.responses)
    order_ids = outcome.order_ids
    statuses = {str(leg.get("status") or "").strip().lower() for leg in legs}
    if statuses == {"filled"}:
        parent_status = "filled"
    elif statuses & {"filled", "partially_filled"}:
        parent_status = "partially_filled"
    elif statuses & {"rejected"}:
        parent_status = "rejected"
    else:
        parent_status = next(iter(statuses), "") or "canceled"
    return {
        "id": order_ids[0] if order_ids else None,
        "status": parent_status,
        "legs": legs,
    }


# --------------------------------------------------------------------------- #
# P6-BE-6 — MONITORING (Phase 7 hand-off placeholder)
# --------------------------------------------------------------------------- #


def monitoring_node(deps: OrchestratorDeps) -> NodeBody:
    """Terminal node: snapshot a :class:`MonitoringState` and hand off to Phase 7.

    A placeholder — it records the portfolio / hedge snapshot for the cycle and
    persists one ``monitoring_state`` row (when an engine is configured) so the
    cycle ends discoverable. It makes no trades and adds no routing; Phase 7
    replaces the body with the real Level-1 / Level-2 monitoring loop.
    """
    if deps.engine is None:
        logger.warning("MONITORING node built with engine=None; monitoring_state will not persist")

    def _run(state: OrchestratorState) -> dict[str, Any]:
        ctx = _context(state)
        exec_result = state.get("execution_result")
        cycle_id = state.get("cycle_id") or (ctx.cycle_id if ctx is not None else "unknown")

        state_snapshot = MonitoringState(
            cycle_id=cycle_id,
            as_of=datetime.now(timezone.utc),
            portfolio_value=ctx.portfolio_state.total_value if ctx is not None else None,
            drawdown=ctx.portfolio_state.drawdown if ctx is not None else None,
            volatility=ctx.portfolio_state.volatility if ctx is not None else None,
            gross_exposure=ctx.portfolio_state.gross_exposure if ctx is not None else None,
            hedge_ratio=ctx.current_hedge.hedge_ratio if ctx is not None else None,
            target_hedge_ratio=ctx.objective.target_hedge_ratio if ctx is not None else None,
            trigger_history=[],
            active_triggers=[],
            reassessment_recommended=False,
        )
        _persist_monitoring(deps.engine, state_snapshot, exec_result)
        return _stamp(WorkflowNode.MONITORING, monitoring_state=state_snapshot)

    _run.__name__ = "monitoring_node"
    return _run


def _persist_monitoring(
    engine: "Engine | None", snapshot: MonitoringState, exec_result: Any
) -> None:
    """Best-effort ``monitoring_state`` write — a persist failure at the terminal
    node must not destroy an otherwise complete cycle."""
    if engine is None:
        return
    try:
        from backend.db.monitoring_repo import (
            MonitoringRepository,
            MonitoringStateRecord,
        )

        detail: dict[str, Any] = {"source": "P6-BE-6 monitoring hand-off placeholder"}
        if exec_result is not None:
            detail["execution_status"] = getattr(
                getattr(exec_result, "status", None), "value", str(exec_result)
            )
        MonitoringRepository(engine).save_state(
            MonitoringStateRecord(
                cycle_id=snapshot.cycle_id,
                current_hedge=_decimal(snapshot.hedge_ratio),
                target_hedge=_decimal(snapshot.target_hedge_ratio),
                cooldown_until=snapshot.cooldown_until,
                trigger_history=[t.model_dump(mode="json") for t in snapshot.trigger_history],
                monitoring_status="ACTIVE",
                detail=detail,
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "MONITORING node: could not persist MonitoringState for %s", snapshot.cycle_id
        )


# --------------------------------------------------------------------------- #
# routing — pure functions P6-BE-7 will attach as conditional edges
# --------------------------------------------------------------------------- #


def route_after_analyzing(state: OrchestratorState) -> str:
    """Next node after ``ANALYZING``.

    ``STRATEGY_EVALUATION`` on a healthy run; ``MONITORING`` when the node
    produced no :class:`HedgeContext` — a hard failure (which set
    ``route=MONITORING``) or a ``CRITICAL`` classification (which also set
    ``halted``). Skipping straight to the terminal node is what "the cycle halts
    before ``EXECUTION``" means for an upstream failure (BRD §31).
    """
    if state.get("halted") or state.get("route") == _MONITORING:
        return _MONITORING
    if _context(state) is None:
        return _MONITORING
    return _STRATEGY


def route_after_strategy(state: OrchestratorState) -> str:
    """Next node after ``STRATEGY_EVALUATION``.

    ``MONITORING`` for a ``NO_TRADE`` / ``REASSESS`` decision (or a missing one),
    ``RISK_CHECK`` otherwise. Reads the decision itself, not the advisory
    ``route`` hint.
    """
    decision = state.get("strategy_decision")
    if decision is None or decision.decision in _SKIP_STRATEGY:
        return _MONITORING
    return _RISK_CHECK


def route_after_risk(state: OrchestratorState) -> str:
    """Next node after ``RISK_CHECK``.

    ``EXECUTION`` only on an ``APPROVE`` / ``MODIFY`` verdict with an approved
    hypothesis, ``MONITORING`` for anything else (``REJECT``, a missing decision,
    a routed no-op).
    """
    decision = state.get("risk_decision")
    if (
        decision is None
        or decision.verdict not in _EXECUTABLE_VERDICTS
        or decision.approved_hypothesis is None
    ):
        return _MONITORING
    return _EXECUTION


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #


def _initial_node(state: OrchestratorState) -> dict[str, Any]:
    """``INITIAL`` stays a marker — it just records the entry."""
    return _stamp(WorkflowNode.INITIAL)


def _resolve_transition_sink(deps: OrchestratorDeps) -> TransitionSink | None:
    """Where node ENTER/EXIT is recorded (P6-BE-10) — explicit sink, else one over
    the engine, else nothing."""
    if deps.transition_sink is not None:
        return deps.transition_sink
    if deps.engine is not None and deps.persist_transitions:
        try:
            return WorkflowTransitionSink(deps.engine)
        except Exception:  # noqa: BLE001 - a missing table must not stop the graph building
            logger.exception(
                "could not build a WorkflowTransitionSink; node transitions will not persist"
            )
    return None


def build_nodes(deps: OrchestratorDeps) -> dict[str, NodeBody]:
    """The six node bodies keyed by :class:`WorkflowNode` value, built from ``deps``.

    Every body is wrapped with the P6-BE-10 persistence hook when a transition
    sink is available (an explicit ``deps.transition_sink`` or one built over
    ``deps.engine``), so entering and leaving each node writes a timestamped
    ``workflow_state`` / ``workflow_transitions`` row.
    """
    bodies: dict[str, NodeBody] = {
        WorkflowNode.INITIAL.value: _initial_node,
        WorkflowNode.ANALYZING.value: analyzing_node(deps),
        WorkflowNode.STRATEGY_EVALUATION.value: strategy_evaluation_node(deps),
        WorkflowNode.RISK_CHECK.value: risk_check_node(deps),
        WorkflowNode.EXECUTION.value: execution_node(deps),
        WorkflowNode.MONITORING.value: monitoring_node(deps),
    }
    return wrap_with_transition_hook(bodies, _resolve_transition_sink(deps))
