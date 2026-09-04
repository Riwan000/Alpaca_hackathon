"""Kill-and-restart mid-cycle resumes from the last persisted node — task P6-DB-2.

Tech-Stack §21: "The system should persist important state so that a restart does
not lose the portfolio's decision history."

Each test drives :class:`backend.agents.orchestrator.CycleRunner` twice against
one migrated SQLite database — the second run standing in for a fresh process
after a ``Ctrl-C``. The bar:

* the restart **resumes** — it does not replay ``INITIAL`` or re-open the cycle;
* ``EXECUTION`` runs its side effect **exactly once** — no duplicate ``orders``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.agents.orchestrator import (
    CYCLE_NODES,
    CycleContext,
    CycleRunner,
    NodeFn,
    run_cycle,
)
from backend.db import OVERRIDE_ENV_VAR, normalize_driver
from backend.db.orders_repo import OrderRecord, OrderRepository
from backend.db.workflow_repo import WorkflowRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"

pytestmark = pytest.mark.integration


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """A scratch SQLite database migrated to head."""
    db_url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'resume.db'}"
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"migration failed:\n{proc.stdout}\n{proc.stderr}"
    eng = create_engine(normalize_driver(db_url), future=True)
    try:
        yield eng
    finally:
        eng.dispose()


def _counting_nodes(calls: Counter[str]) -> dict[str, NodeFn]:
    """One body per non-execution node that just tallies how often it ran."""

    def make(name: str) -> NodeFn:
        def body(_ctx: CycleContext) -> None:
            calls[name] += 1

        return body

    return {
        name: make(name)
        for name in ("INITIAL", "ANALYZING", "STRATEGY_EVALUATION", "RISK_CHECK", "MONITORING")
    }


def _idempotent_execution(calls: Counter[str]) -> NodeFn:
    """An ``EXECUTION`` body: submit one order per cycle, and never a second."""

    def body(ctx: CycleContext) -> dict[str, object]:
        orders = OrderRepository(ctx.engine)
        if orders.list_for_cycle(ctx.cycle_id):
            calls["EXECUTION_SKIP"] += 1
            return {"skipped": "order already on file"}
        orders.create(
            OrderRecord(cycle_id=ctx.cycle_id, order_class="MLEG", status="SUBMITTED")
        )
        calls["EXECUTION_SUBMIT"] += 1
        return {"submitted": True}

    return body


def test_interrupt_during_analyzing_resumes_without_restarting(engine: Engine) -> None:
    cycle_id = "cyc_resume_analyzing"
    calls: Counter[str] = Counter()
    repo = WorkflowRepository(engine)

    # --- run 1: Ctrl-C fires inside ANALYZING, before it checkpoints ---------- #
    def analyzing_then_interrupt(_ctx: CycleContext) -> None:
        calls["ANALYZING"] += 1
        raise KeyboardInterrupt

    run1_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "ANALYZING": analyzing_then_interrupt,
        "EXECUTION": _idempotent_execution(calls),
    }

    with pytest.raises(KeyboardInterrupt):
        CycleRunner(engine, nodes=run1_nodes).run(cycle_id)

    halted = repo.get_state(cycle_id)
    assert halted is not None
    assert halted.current_node == "INITIAL"  # the last node that actually finished
    assert halted.status == "HALTED"
    assert calls["ANALYZING"] == 1
    assert calls["EXECUTION_SUBMIT"] == 0
    assert OrderRepository(engine).count() == 0

    # --- run 2: fresh process, ANALYZING now succeeds ------------------------- #
    run2_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "EXECUTION": _idempotent_execution(calls),
    }
    final = CycleRunner(engine, nodes=run2_nodes).run(cycle_id)

    assert final.current_node == "COMPLETED"
    assert final.status == "COMPLETED"
    assert calls["INITIAL"] == 1  # not replayed — resumed, did not restart
    assert calls["ANALYZING"] == 2  # re-ran once (interrupted before its checkpoint)
    assert calls["EXECUTION_SUBMIT"] == 1  # the side effect ran exactly once
    assert OrderRepository(engine).count() == 1

    to_nodes = [t.to_node for t in repo.get_transitions(cycle_id)]
    assert to_nodes[-1] == "COMPLETED"
    assert to_nodes.count("EXECUTION") == 1


def test_no_duplicate_orders_when_killed_right_after_execution(engine: Engine) -> None:
    cycle_id = "cyc_resume_execution"
    calls: Counter[str] = Counter()
    repo = WorkflowRepository(engine)

    # --- run 1: EXECUTION submits its order, then the process dies before the
    #            runner can checkpoint the EXECUTION node ------------------- #
    def execution_then_die(ctx: CycleContext) -> None:
        orders = OrderRepository(ctx.engine)
        if not orders.list_for_cycle(ctx.cycle_id):
            orders.create(
                OrderRecord(cycle_id=ctx.cycle_id, order_class="MLEG", status="SUBMITTED")
            )
            calls["EXECUTION_SUBMIT"] += 1
        raise KeyboardInterrupt

    run1_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "EXECUTION": execution_then_die,
    }

    with pytest.raises(KeyboardInterrupt):
        CycleRunner(engine, nodes=run1_nodes).run(cycle_id)

    halted = repo.get_state(cycle_id)
    assert halted is not None
    assert halted.current_node == "RISK_CHECK"  # EXECUTION never checkpointed
    assert halted.status == "HALTED"
    assert calls["EXECUTION_SUBMIT"] == 1
    assert OrderRepository(engine).count() == 1

    # --- run 2: fresh process. EXECUTION is re-entered (its checkpoint is
    #            missing) but its idempotency guard sees the existing order. -- #
    run2_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "EXECUTION": _idempotent_execution(calls),
    }
    final = CycleRunner(engine, nodes=run2_nodes).run(cycle_id)

    assert final.current_node == "COMPLETED"
    assert final.status == "COMPLETED"
    assert calls["INITIAL"] == 1  # not replayed
    assert calls["EXECUTION_SUBMIT"] == 1  # still just the one submit
    assert calls["EXECUTION_SKIP"] == 1  # resume hit the guard
    assert OrderRepository(engine).count() == 1  # no duplicate order
    assert len(OrderRepository(engine).list_for_cycle(cycle_id)) == 1


def test_restart_with_no_cycle_id_resumes_the_interrupted_cycle(engine: Engine) -> None:
    calls: Counter[str] = Counter()
    repo = WorkflowRepository(engine)

    def analyzing_then_interrupt(_ctx: CycleContext) -> None:
        calls["ANALYZING"] += 1
        raise KeyboardInterrupt

    run1_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "ANALYZING": analyzing_then_interrupt,
        "EXECUTION": _idempotent_execution(calls),
    }
    with pytest.raises(KeyboardInterrupt):
        CycleRunner(engine, nodes=run1_nodes).run()  # cycle_id minted internally

    interrupted = repo.latest_unfinished_cycle()
    assert interrupted is not None  # a cold start can find the halted cycle

    run2_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "EXECUTION": _idempotent_execution(calls),
    }
    final = CycleRunner(engine, nodes=run2_nodes).run()  # no id → resume the halted one

    assert final.cycle_id == interrupted
    assert final.current_node == "COMPLETED"
    assert calls["INITIAL"] == 1  # resumed, not restarted
    assert OrderRepository(engine).count() == 1
    assert repo.latest_unfinished_cycle() is None  # nothing left to resume


def test_run_cycle_with_default_nodes_persists_every_transition(engine: Engine) -> None:
    repo = WorkflowRepository(engine)

    final = run_cycle(engine, "cyc_default")  # zero custom nodes — placeholders

    assert final.current_node == "COMPLETED"
    assert final.status == "COMPLETED"
    to_nodes = [t.to_node for t in repo.get_transitions("cyc_default")]
    assert to_nodes == [*CYCLE_NODES, "COMPLETED"]


def test_interrupt_inside_initial_still_leaves_a_resumable_cycle(engine: Engine) -> None:
    calls: Counter[str] = Counter()
    repo = WorkflowRepository(engine)

    def initial_then_interrupt(_ctx: CycleContext) -> None:
        calls["INITIAL"] += 1
        raise KeyboardInterrupt

    run1_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "INITIAL": initial_then_interrupt,
        "EXECUTION": _idempotent_execution(calls),
    }
    with pytest.raises(KeyboardInterrupt):
        CycleRunner(engine, nodes=run1_nodes).run()  # brand-new auto-minted id

    interrupted = repo.latest_unfinished_cycle()
    assert interrupted is not None  # not orphaned despite dying in the first node
    halted = repo.get_state(interrupted)
    assert halted is not None
    assert halted.current_node == "INITIAL"
    assert halted.status == "HALTED"

    run2_nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "EXECUTION": _idempotent_execution(calls),
    }
    final = CycleRunner(engine, nodes=run2_nodes).run(interrupted)

    assert final.current_node == "COMPLETED"
    assert calls["INITIAL"] == 1  # INITIAL is a marker — resume continues at ANALYZING
    assert calls["ANALYZING"] == 1
    assert OrderRepository(engine).count() == 1


def test_unknown_node_name_is_rejected(engine: Engine) -> None:
    with pytest.raises(ValueError, match="unknown node name"):
        CycleRunner(engine, nodes={"EXECUTON": lambda _ctx: None})  # typo


def test_completed_cycle_is_a_safe_noop_on_rerun(engine: Engine) -> None:
    cycle_id = "cyc_resume_done"
    calls: Counter[str] = Counter()
    nodes: dict[str, NodeFn] = {
        **_counting_nodes(calls),
        "EXECUTION": _idempotent_execution(calls),
    }

    first = CycleRunner(engine, nodes=nodes).run(cycle_id)
    assert first.current_node == "COMPLETED"

    before = dict(calls)
    again = CycleRunner(engine, nodes=nodes).run(cycle_id)

    assert again.current_node == "COMPLETED"
    assert dict(calls) == before  # no node re-ran
    assert OrderRepository(engine).count() == 1
