"""Database schema tests — task P1-DB-3+.

Tests that running Alembic migrations produces the expected tables, columns,
types, primary keys, foreign keys, and constraints.
"""

from __future__ import annotations

import datetime
import decimal
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import (
    MetaData,
    Table,
    create_engine,
    inspect,
    insert,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError

from backend.db import OVERRIDE_ENV_VAR, normalize_driver

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "backend" / "alembic.ini"


def _scratch_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'scratch.db'}"


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(_ALEMBIC_INI), *args],
        cwd=_REPO_ROOT,
        env={**os.environ, OVERRIDE_ENV_VAR: db_url},
        capture_output=True,
        text=True,
        check=False,
    )


def test_portfolio_snapshots(tmp_path: Path) -> None:
    """Task P1-DB-3: portfolio_snapshots table creation and schema validation."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "portfolio_snapshots" in tables, (
            f"Table 'portfolio_snapshots' not found in database; found {tables}"
        )

        pk_constraint = inspector.get_pk_constraint("portfolio_snapshots")
        assert pk_constraint["constrained_columns"] == ["id"], (
            f"Expected primary key ['id'], got {pk_constraint['constrained_columns']}"
        )

        columns = inspector.get_columns("portfolio_snapshots")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "cycle_id",
            "ts",
            "total_value",
            "cash",
            "equity",
            "buying_power",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from portfolio_snapshots"

        from sqlalchemy.types import BigInteger, DateTime, Integer, Numeric, String

        assert isinstance(col_by_name["id"]["type"], (Integer, BigInteger))
        assert isinstance(col_by_name["cycle_id"]["type"], String)
        assert isinstance(col_by_name["ts"]["type"], DateTime)
        for num_col in ["total_value", "cash", "equity", "buying_power"]:
            assert isinstance(col_by_name[num_col]["type"], Numeric)

        metadata = MetaData()
        portfolio_snapshots_table = Table("portfolio_snapshots", metadata, autoload_with=engine)

        with engine.begin() as conn:
            stmt = insert(portfolio_snapshots_table).values(
                cycle_id="cycle_test_001",
                ts=datetime.datetime.now(datetime.timezone.utc),
                total_value=decimal.Decimal("100000.5000"),
                cash=decimal.Decimal("25000.2500"),
                equity=decimal.Decimal("75000.2500"),
                buying_power=decimal.Decimal("50000.0000"),
            )
            result = conn.execute(stmt)
            inserted_id = result.inserted_primary_key[0]
            assert inserted_id is not None

            select_stmt = select(portfolio_snapshots_table).where(
                portfolio_snapshots_table.c.id == inserted_id
            )
            row = conn.execute(select_stmt).mappings().one()
            assert row["cycle_id"] == "cycle_test_001"
            assert row["total_value"] == decimal.Decimal("100000.5000")
            assert row["cash"] == decimal.Decimal("25000.2500")

    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0001_baseline", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0001_baseline` failed:\n{down.stdout}\n{down.stderr}"
    )


def test_positions(tmp_path: Path) -> None:
    """Task P1-DB-4: positions table and FK constraint to portfolio_snapshots."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "positions" in tables, f"Table 'positions' not found in database; found {tables}"

        pk_constraint = inspector.get_pk_constraint("positions")
        assert pk_constraint["constrained_columns"] == ["id"]

        columns = inspector.get_columns("positions")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "snapshot_id",
            "symbol",
            "qty",
            "avg_price",
            "market_value",
            "asset_class",
            "side",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from positions"

        fks = inspector.get_foreign_keys("positions")
        assert len(fks) >= 1, "Expected at least one foreign key on positions"
        snapshot_fk = next((fk for fk in fks if fk.get("constrained_columns") == ["snapshot_id"]), None)
        assert snapshot_fk is not None, f"Foreign key on snapshot_id not found: {fks}"
        assert snapshot_fk["referred_table"] == "portfolio_snapshots"
        assert snapshot_fk["referred_columns"] == ["id"]

        # Insert a parent snapshot and child position
        metadata = MetaData()
        portfolio_snapshots_table = Table("portfolio_snapshots", metadata, autoload_with=engine)
        positions_table = Table("positions", metadata, autoload_with=engine)

        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA foreign_keys = ON;")

        # Orphan insert should fail when foreign keys are enforced
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                if engine.dialect.name == "sqlite":
                    conn.exec_driver_sql("PRAGMA foreign_keys = ON;")
                conn.execute(
                    insert(positions_table).values(
                        snapshot_id=999999,
                        symbol="AAPL",
                        qty=decimal.Decimal("10.0000"),
                        avg_price=decimal.Decimal("150.0000"),
                        market_value=decimal.Decimal("1500.0000"),
                        asset_class="us_equity",
                        side="long",
                    )
                )

        with engine.begin() as conn:
            snap_res = conn.execute(
                insert(portfolio_snapshots_table).values(
                    cycle_id="cycle_pos_001",
                    ts=datetime.datetime.now(datetime.timezone.utc),
                    total_value=decimal.Decimal("10000.0000"),
                    cash=decimal.Decimal("8500.0000"),
                    equity=decimal.Decimal("1500.0000"),
                    buying_power=decimal.Decimal("8500.0000"),
                )
            )
            snap_id = snap_res.inserted_primary_key[0]

            pos_res = conn.execute(
                insert(positions_table).values(
                    snapshot_id=snap_id,
                    symbol="AAPL",
                    qty=decimal.Decimal("10.0000"),
                    avg_price=decimal.Decimal("150.0000"),
                    market_value=decimal.Decimal("1500.0000"),
                    asset_class="us_equity",
                    side="long",
                )
            )
            pos_id = pos_res.inserted_primary_key[0]
            assert pos_id is not None

    finally:
        engine.dispose()

    # Verify downgrade
    down = _run_alembic("downgrade", "0002_portfolio_snapshots", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0002_portfolio_snapshots` failed:\n{down.stdout}\n{down.stderr}"
    )


def test_agent_runs(tmp_path: Path) -> None:
    """Task P1-DB-5: agent_runs table schema and jsonb handling."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "agent_runs" in tables, f"Table 'agent_runs' not found in database; found {tables}"

        pk_constraint = inspector.get_pk_constraint("agent_runs")
        assert pk_constraint["constrained_columns"] == ["id"]

        columns = inspector.get_columns("agent_runs")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "cycle_id",
            "agent_name",
            "inputs",
            "outputs",
            "error",
            "started_at",
            "finished_at",
            "duration_ms",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from agent_runs"

        # Check nullable columns
        assert col_by_name["inputs"]["nullable"] is True
        assert col_by_name["outputs"]["nullable"] is True
        assert col_by_name["error"]["nullable"] is True
        assert col_by_name["finished_at"]["nullable"] is True
        assert col_by_name["duration_ms"]["nullable"] is True

        from sqlalchemy.types import Integer

        assert isinstance(col_by_name["duration_ms"]["type"], Integer)

        # Verify row insertion with json inputs and nullable outputs
        metadata = MetaData()
        agent_runs_table = Table("agent_runs", metadata, autoload_with=engine)

        with engine.begin() as conn:
            stmt = insert(agent_runs_table).values(
                cycle_id="cycle_agent_001",
                agent_name="market_agent",
                inputs={"symbols": ["AAPL", "SPY"], "lookback_days": 30},
                outputs=None,
                error=None,
                started_at=datetime.datetime.now(datetime.timezone.utc),
                finished_at=None,
                duration_ms=None,
            )
            res = conn.execute(stmt)
            inserted_id = res.inserted_primary_key[0]
            assert inserted_id is not None

            select_stmt = select(agent_runs_table).where(agent_runs_table.c.id == inserted_id)
            row = conn.execute(select_stmt).mappings().one()
            assert row["agent_name"] == "market_agent"
            assert row["inputs"] == {"symbols": ["AAPL", "SPY"], "lookback_days": 30}
            assert row["outputs"] is None

    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0003_positions", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0003_positions` failed:\n{down.stdout}\n{down.stderr}"
    )


def test_strategy_hypotheses(tmp_path: Path) -> None:
    """Task P1-DB-6: strategy_hypotheses table schema and verdict enum constraints."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "strategy_hypotheses" in tables, f"Table 'strategy_hypotheses' not found; found {tables}"

        pk_constraint = inspector.get_pk_constraint("strategy_hypotheses")
        assert pk_constraint["constrained_columns"] == ["id"]

        columns = inspector.get_columns("strategy_hypotheses")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "cycle_id",
            "strategy_type",
            "verdict",
            "legs",
            "metrics",
            "rejection_reason",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from strategy_hypotheses"

        # Check nullable columns
        assert col_by_name["legs"]["nullable"] is True
        assert col_by_name["metrics"]["nullable"] is True
        assert col_by_name["rejection_reason"]["nullable"] is True
        assert col_by_name["verdict"]["nullable"] is False

        metadata = MetaData()
        table = Table("strategy_hypotheses", metadata, autoload_with=engine)

        # 1. Valid insert
        with engine.begin() as conn:
            stmt = insert(table).values(
                cycle_id="cycle_strat_001",
                strategy_type="delta_neutral_collar",
                verdict="ACCEPTED",
                legs=[{"symbol": "SPY_240920P00500000", "ratio": 1}],
                metrics={"delta": -0.45, "cost": 120.0},
                rejection_reason=None,
            )
            res = conn.execute(stmt)
            inserted_id = res.inserted_primary_key[0]
            assert inserted_id is not None

        # 2. Invalid verdict insert should fail
        from sqlalchemy.exc import DBAPIError
        with pytest.raises((IntegrityError, DBAPIError, Exception)):
            with engine.begin() as conn:
                conn.execute(
                    insert(table).values(
                        cycle_id="cycle_strat_002",
                        strategy_type="delta_neutral_collar",
                        verdict="INVALID_VERDICT_VALUE",
                        legs=None,
                        metrics=None,
                        rejection_reason=None,
                    )
                )

    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0004_agent_runs", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0004_agent_runs` failed:\n{down.stdout}\n{down.stderr}"
    )


def test_strategy_decisions(tmp_path: Path) -> None:
    """Task P1-DB-7: strategy_decisions table schema, FK to strategy_hypotheses, and NO_TRADE."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "strategy_decisions" in tables, f"Table 'strategy_decisions' not found; found {tables}"

        pk_constraint = inspector.get_pk_constraint("strategy_decisions")
        assert pk_constraint["constrained_columns"] == ["id"]

        columns = inspector.get_columns("strategy_decisions")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "cycle_id",
            "action",
            "selected_hypothesis_id",
            "rationale",
            "alternatives",
            "comparison",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from strategy_decisions"

        assert col_by_name["selected_hypothesis_id"]["nullable"] is True

        fks = inspector.get_foreign_keys("strategy_decisions")
        hypo_fk = next(
            (fk for fk in fks if fk.get("constrained_columns") == ["selected_hypothesis_id"]), None
        )
        assert hypo_fk is not None, f"FK on selected_hypothesis_id not found in {fks}"
        assert hypo_fk["referred_table"] == "strategy_hypotheses"
        assert hypo_fk["referred_columns"] == ["id"]

        metadata = MetaData()
        decisions_table = Table("strategy_decisions", metadata, autoload_with=engine)
        hypotheses_table = Table("strategy_hypotheses", metadata, autoload_with=engine)

        # 1. NO_TRADE decision with null selected_hypothesis_id
        with engine.begin() as conn:
            res_notrade = conn.execute(
                insert(decisions_table).values(
                    cycle_id="cycle_dec_001",
                    action="NO_TRADE",
                    selected_hypothesis_id=None,
                    rationale="Portfolio risk is within acceptable boundaries; hedging not needed.",
                    alternatives=[],
                    comparison={},
                )
            )
            assert res_notrade.inserted_primary_key[0] is not None

        # 2. HEDGE decision with linked hypothesis
        with engine.begin() as conn:
            hypo_res = conn.execute(
                insert(hypotheses_table).values(
                    cycle_id="cycle_dec_002",
                    strategy_type="delta_neutral_collar",
                    verdict="ACCEPTED",
                    legs=[{"symbol": "SPY_P", "ratio": 1}],
                    metrics={"cost": 100},
                    rejection_reason=None,
                )
            )
            hypo_id = hypo_res.inserted_primary_key[0]

            res_hedge = conn.execute(
                insert(decisions_table).values(
                    cycle_id="cycle_dec_002",
                    action="HEDGE",
                    selected_hypothesis_id=hypo_id,
                    rationale="High market beta detected; executing collar.",
                    alternatives=[{"type": "tail_risk_put", "reason": "too expensive"}],
                    comparison={"cost_efficiency": 0.85},
                )
            )
            assert res_hedge.inserted_primary_key[0] is not None

    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0005_strategy_hypotheses", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0005_strategy_hypotheses` failed:\n{down.stdout}\n{down.stderr}"
    )


def test_risk_checks(tmp_path: Path) -> None:
    """Task P1-DB-8: risk_checks table schema and four JSONB columns."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "risk_checks" in tables, f"Table 'risk_checks' not found; found {tables}"

        pk_constraint = inspector.get_pk_constraint("risk_checks")
        assert pk_constraint["constrained_columns"] == ["id"]

        columns = inspector.get_columns("risk_checks")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "cycle_id",
            "verdict",
            "checks",
            "violations",
            "warnings",
            "modifications",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from risk_checks"

        # Check all four jsonb columns are present and nullable
        for jsonb_col in ["checks", "violations", "warnings", "modifications"]:
            assert col_by_name[jsonb_col]["nullable"] is True

        metadata = MetaData()
        risk_table = Table("risk_checks", metadata, autoload_with=engine)

        with engine.begin() as conn:
            res = conn.execute(
                insert(risk_table).values(
                    cycle_id="cycle_risk_001",
                    verdict="MODIFIED",
                    checks=[{"check": "max_drawdown", "passed": True}],
                    violations=[],
                    warnings=["delta exposure near upper boundary"],
                    modifications={"qty": 5},
                )
            )
            inserted_id = res.inserted_primary_key[0]
            assert inserted_id is not None

            select_stmt = select(risk_table).where(risk_table.c.id == inserted_id)
            row = conn.execute(select_stmt).mappings().one()
            assert row["verdict"] == "MODIFIED"
            assert row["modifications"] == {"qty": 5}
            assert row["warnings"] == ["delta exposure near upper boundary"]

    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0006_strategy_decisions", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0006_strategy_decisions` failed:\n{down.stdout}\n{down.stderr}"
    )


def test_orders(tmp_path: Path) -> None:
    """Task P1-DB-9: orders table schema, status constraints, and unique-nullable broker_order_id."""
    db_url = _scratch_url(tmp_path)

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "orders" in tables, f"Table 'orders' not found; found {tables}"

        pk_constraint = inspector.get_pk_constraint("orders")
        assert pk_constraint["constrained_columns"] == ["id"]

        columns = inspector.get_columns("orders")
        col_by_name = {c["name"]: c for c in columns}

        expected_columns = [
            "id",
            "cycle_id",
            "broker_order_id",
            "class",
            "legs",
            "status",
            "submitted_at",
        ]
        for col_name in expected_columns:
            assert col_name in col_by_name, f"Column '{col_name}' missing from orders"

        assert col_by_name["broker_order_id"]["nullable"] is True
        assert col_by_name["legs"]["nullable"] is True
        assert col_by_name["status"]["nullable"] is False

        metadata = MetaData()
        orders_table = Table("orders", metadata, autoload_with=engine)

        # 1. Insert two rows with NULL broker_order_id (must coexist)
        with engine.begin() as conn:
            res1 = conn.execute(
                insert(orders_table).values(
                    cycle_id="cycle_ord_001",
                    broker_order_id=None,
                    status="PENDING",
                    legs=[{"symbol": "SPY", "qty": 10}],
                    submitted_at=datetime.datetime.now(datetime.timezone.utc),
                    **{"class": "simple"},
                )
            )
            res2 = conn.execute(
                insert(orders_table).values(
                    cycle_id="cycle_ord_001",
                    broker_order_id=None,
                    status="PENDING",
                    legs=[{"symbol": "AAPL", "qty": 5}],
                    submitted_at=datetime.datetime.now(datetime.timezone.utc),
                    **{"class": "simple"},
                )
            )
            assert res1.inserted_primary_key[0] is not None
            assert res2.inserted_primary_key[0] is not None
            assert res1.inserted_primary_key[0] != res2.inserted_primary_key[0]

        # 2. Insert with broker_order_id
        with engine.begin() as conn:
            conn.execute(
                insert(orders_table).values(
                    cycle_id="cycle_ord_002",
                    broker_order_id="broker_order_xyz_1",
                    status="SUBMITTED",
                    legs=None,
                    submitted_at=datetime.datetime.now(datetime.timezone.utc),
                    **{"class": "bracket"},
                )
            )

        # Duplicate broker_order_id must fail
        with pytest.raises((IntegrityError, Exception)):
            with engine.begin() as conn:
                conn.execute(
                    insert(orders_table).values(
                        cycle_id="cycle_ord_003",
                        broker_order_id="broker_order_xyz_1",
                        status="SUBMITTED",
                        legs=None,
                        submitted_at=datetime.datetime.now(datetime.timezone.utc),
                        **{"class": "bracket"},
                    )
                )

        # Invalid status must fail
        with pytest.raises((IntegrityError, Exception)):
            with engine.begin() as conn:
                conn.execute(
                    insert(orders_table).values(
                        cycle_id="cycle_ord_004",
                        broker_order_id="broker_order_xyz_2",
                        status="INVALID_STATUS",
                        legs=None,
                        submitted_at=datetime.datetime.now(datetime.timezone.utc),
                        **{"class": "simple"},
                    )
                )

    finally:
        engine.dispose()

    down = _run_alembic("downgrade", "0007_risk_checks", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0007_risk_checks` failed:\n{down.stdout}\n{down.stderr}"
    )





