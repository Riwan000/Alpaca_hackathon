"""Database schema tests — task P1-DB-3+.

Tests that running Alembic migrations produces the expected tables, columns,
types, primary keys, and constraints.
"""

from __future__ import annotations

import datetime
import decimal
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, insert, select, Table, MetaData

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

    # 1. Run migrations up to head
    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, f"`alembic upgrade head` failed:\n{up.stdout}\n{up.stderr}"

    engine = create_engine(normalize_driver(db_url))
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "portfolio_snapshots" in tables, (
            f"Table 'portfolio_snapshots' not found in database; found {tables}"
        )

        # 2. Verify Primary Key
        pk_constraint = inspector.get_pk_constraint("portfolio_snapshots")
        assert pk_constraint["constrained_columns"] == ["id"], (
            f"Expected primary key ['id'], got {pk_constraint['constrained_columns']}"
        )

        # 3. Verify Columns
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

        # Check types
        from sqlalchemy.types import BigInteger, DateTime, Integer, Numeric, String

        assert isinstance(col_by_name["id"]["type"], (Integer, BigInteger)), (
            f"id type unexpected: {col_by_name['id']['type']}"
        )
        assert isinstance(col_by_name["cycle_id"]["type"], String), (
            f"cycle_id type unexpected: {col_by_name['cycle_id']['type']}"
        )
        assert isinstance(col_by_name["ts"]["type"], DateTime), (
            f"ts type unexpected: {col_by_name['ts']['type']}"
        )
        for num_col in ["total_value", "cash", "equity", "buying_power"]:
            assert isinstance(col_by_name[num_col]["type"], Numeric), (
                f"{num_col} type unexpected: {col_by_name[num_col]['type']}"
            )

        # 4. Verify insertion and retrieval
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

            # Query back
            select_stmt = select(portfolio_snapshots_table).where(
                portfolio_snapshots_table.c.id == inserted_id
            )
            row = conn.execute(select_stmt).mappings().one()
            assert row["cycle_id"] == "cycle_test_001"
            assert row["total_value"] == decimal.Decimal("100000.5000")
            assert row["cash"] == decimal.Decimal("25000.2500")

    finally:
        engine.dispose()

    # 5. Verify downgrade unwinds cleanly
    down = _run_alembic("downgrade", "0001_baseline", db_url=db_url)
    assert down.returncode == 0, (
        f"`alembic downgrade 0001_baseline` failed:\n{down.stdout}\n{down.stderr}"
    )

    engine = create_engine(normalize_driver(db_url))
    try:
        tables = inspect(engine).get_table_names()
        assert "portfolio_snapshots" not in tables, (
            f"Table 'portfolio_snapshots' still exists after downgrade: {tables}"
        )
    finally:
        engine.dispose()
