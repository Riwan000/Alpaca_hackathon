"""Demo portfolio seed loader — task P1-DB-15.

Loads the known baseline demo portfolio (one portfolio snapshot + its positions)
into the target database (Neon PostgreSQL or SQLite scratch database).

Usage:
    python -m backend.seed
    python -m backend.seed --url postgresql://...
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import sys
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, delete, insert, select

from backend.db import migration_url, normalize_driver

# Canonical demo portfolio fixture
DEMO_SNAPSHOT: dict[str, Any] = {
    "cycle_id": "cycle_demo_baseline",
    "ts": datetime.datetime(2026, 9, 2, 12, 0, 0, tzinfo=datetime.timezone.utc),
    "total_value": decimal.Decimal("100000.0000"),
    "cash": decimal.Decimal("25000.0000"),
    "equity": decimal.Decimal("75000.0000"),
    "buying_power": decimal.Decimal("50000.0000"),
}

DEMO_POSITIONS: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "qty": decimal.Decimal("100.0000"),
        "avg_price": decimal.Decimal("225.0000"),
        "market_value": decimal.Decimal("22500.0000"),
        "asset_class": "us_equity",
        "side": "long",
    },
    {
        "symbol": "NVDA",
        "qty": decimal.Decimal("150.0000"),
        "avg_price": decimal.Decimal("120.0000"),
        "market_value": decimal.Decimal("18000.0000"),
        "asset_class": "us_equity",
        "side": "long",
    },
    {
        "symbol": "MSFT",
        "qty": decimal.Decimal("50.0000"),
        "avg_price": decimal.Decimal("410.0000"),
        "market_value": decimal.Decimal("20500.0000"),
        "asset_class": "us_equity",
        "side": "long",
    },
    {
        "symbol": "SPY",
        "qty": decimal.Decimal("25.0000"),
        "avg_price": decimal.Decimal("560.0000"),
        "market_value": decimal.Decimal("14000.0000"),
        "asset_class": "us_equity",
        "side": "long",
    },
]


def seed_demo_portfolio(
    db_url: str | None = None,
    clear_existing: bool = True,
) -> tuple[int, int]:
    """Seed the database with the canonical demo portfolio.

    Returns:
        tuple[int, int]: (inserted snapshot_id, number of positions inserted)
    """
    target_url = normalize_driver(db_url or migration_url())
    engine = create_engine(target_url)

    try:
        metadata = MetaData()
        portfolio_snapshots_table = Table("portfolio_snapshots", metadata, autoload_with=engine)
        positions_table = Table("positions", metadata, autoload_with=engine)

        with engine.begin() as conn:
            if engine.dialect.name == "sqlite":
                conn.exec_driver_sql("PRAGMA foreign_keys = ON;")

            if clear_existing:
                conn.execute(delete(positions_table))
                conn.execute(delete(portfolio_snapshots_table))

            # 1. Insert snapshot
            snap_res = conn.execute(
                insert(portfolio_snapshots_table).values(
                    cycle_id=DEMO_SNAPSHOT["cycle_id"],
                    ts=DEMO_SNAPSHOT["ts"],
                    total_value=DEMO_SNAPSHOT["total_value"],
                    cash=DEMO_SNAPSHOT["cash"],
                    equity=DEMO_SNAPSHOT["equity"],
                    buying_power=DEMO_SNAPSHOT["buying_power"],
                )
            )
            snapshot_id = snap_res.inserted_primary_key[0]

            # 2. Insert positions bound to snapshot_id
            for pos in DEMO_POSITIONS:
                conn.execute(
                    insert(positions_table).values(
                        snapshot_id=snapshot_id,
                        symbol=pos["symbol"],
                        qty=pos["qty"],
                        avg_price=pos["avg_price"],
                        market_value=pos["market_value"],
                        asset_class=pos["asset_class"],
                        side=pos["side"],
                    )
                )

        return snapshot_id, len(DEMO_POSITIONS)

    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the database with the known demo portfolio."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Database connection URL (defaults to migration DSN from settings/.env)",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear existing snapshots/positions before seeding",
    )
    args = parser.parse_args()

    try:
        snap_id, pos_count = seed_demo_portfolio(
            db_url=args.url,
            clear_existing=not args.no_clear,
        )
        print(
            f"[SEED] Successfully seeded demo portfolio snapshot (id={snap_id}) "
            f"with {pos_count} positions."
        )
    except Exception as e:
        print(f"[SEED ERROR] Failed to seed database: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
