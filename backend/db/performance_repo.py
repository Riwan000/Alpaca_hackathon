"""Performance repository — tasks P8-DB-1, P8-DB-2, P8-DB-3.

Tracks time series of portfolio P&L, hedge P&L, net P&L, drawdown, hedge costs,
and unhedged benchmark series for dashboard rendering and comparison.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
from typing import Any

from sqlalchemy import MetaData, Table, desc, insert, select, text
from sqlalchemy.engine import Engine

_PERFORMANCE_TABLE = "performance"


@dataclasses.dataclass(frozen=True)
class PerformanceRecord:
    cycle_id: str
    portfolio_pnl: decimal.Decimal
    hedge_pnl: decimal.Decimal
    net_pnl: decimal.Decimal
    drawdown: decimal.Decimal
    hedge_cost: decimal.Decimal
    benchmark_pnl: decimal.Decimal
    ts: _dt.datetime | None = None
    id: int | None = None


class PerformanceRepository:
    """Synchronous CRUD and aggregate read methods for performance metrics."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._table = Table(_PERFORMANCE_TABLE, MetaData(), autoload_with=engine)

    def save(self, record: PerformanceRecord) -> PerformanceRecord:
        """Persist a performance row, validating net_pnl = portfolio_pnl + hedge_pnl."""
        expected_net = record.portfolio_pnl + record.hedge_pnl
        if abs(record.net_pnl - expected_net) > decimal.Decimal("0.0001"):
            raise ValueError(
                f"Identity net_pnl ({record.net_pnl}) != portfolio_pnl ({record.portfolio_pnl}) + hedge_pnl ({record.hedge_pnl})"
            )

        ts = record.ts or _dt.datetime.now(_dt.timezone.utc)
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._table).values(
                    cycle_id=record.cycle_id,
                    ts=ts,
                    portfolio_pnl=record.portfolio_pnl,
                    hedge_pnl=record.hedge_pnl,
                    net_pnl=record.net_pnl,
                    drawdown=record.drawdown,
                    hedge_cost=record.hedge_cost,
                    benchmark_pnl=record.benchmark_pnl,
                )
            )
            perf_id = int(result.inserted_primary_key[0])

        return dataclasses.replace(record, id=perf_id, ts=ts)

    def get_latest(self) -> PerformanceRecord | None:
        """Return the most recent performance snapshot."""
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._table).order_by(desc(self._table.c.ts), desc(self._table.c.id)).limit(1)
            ).mappings().first()

        if not row:
            return None

        return PerformanceRecord(
            id=row["id"],
            cycle_id=row["cycle_id"],
            portfolio_pnl=row["portfolio_pnl"],
            hedge_pnl=row["hedge_pnl"],
            net_pnl=row["net_pnl"],
            drawdown=row["drawdown"],
            hedge_cost=row["hedge_cost"],
            benchmark_pnl=row["benchmark_pnl"],
            ts=row["ts"],
        )

    def get_series(self, cycle_id: str | None = None, limit: int = 100) -> list[PerformanceRecord]:
        """Return ordered performance time series."""
        query = select(self._table)
        if cycle_id is not None:
            query = query.where(self._table.c.cycle_id == cycle_id)
        query = query.order_by(self._table.c.ts.asc()).limit(limit)

        with self._engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        return [
            PerformanceRecord(
                id=r["id"],
                cycle_id=r["cycle_id"],
                portfolio_pnl=r["portfolio_pnl"],
                hedge_pnl=r["hedge_pnl"],
                net_pnl=r["net_pnl"],
                drawdown=r["drawdown"],
                hedge_cost=r["hedge_cost"],
                benchmark_pnl=r["benchmark_pnl"],
                ts=r["ts"],
            )
            for r in rows
        ]

    def get_benchmark_series(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return timestamped unhedged benchmark comparison points (P8-DB-2)."""
        series = self.get_series(limit=limit)
        return [
            {
                "ts": r.ts.isoformat() if r.ts else None,
                "cycle_id": r.cycle_id,
                "benchmark_pnl": float(r.benchmark_pnl),
                "net_pnl": float(r.net_pnl),
                "hedge_cushion": float(r.net_pnl - r.benchmark_pnl),
            }
            for r in series
        ]

    def get_benchmark_comparison(self, limit: int = 100) -> dict[str, Any]:
        """Hedged vs unhedged comparison with peak-to-trough drawdown (P8-BE-2).

        Walks the ordered performance series building two cumulative-P&L curves —
        ``hedged`` (``net_pnl``) and ``unhedged`` (``benchmark_pnl``) — and the
        running drawdown of each: the drop from that curve's own prior peak, as a
        non-negative dollar magnitude. Before any hedge is on, ``net_pnl`` equals
        ``benchmark_pnl`` at every point, so the two curves — and their
        drawdowns — coincide. Once a protective put pays off inside a drawdown the
        hedged curve troughs shallower, so ``hedged_max_drawdown`` falls below
        ``unhedged_max_drawdown`` and ``is_cushioned`` is ``True`` (BRD §36).
        """
        series = self.get_series(limit=limit)

        points: list[dict[str, Any]] = []
        hedged_peak: decimal.Decimal | None = None
        unhedged_peak: decimal.Decimal | None = None
        hedged_max_dd = decimal.Decimal("0")
        unhedged_max_dd = decimal.Decimal("0")
        total_hedge_cost = decimal.Decimal("0")

        for r in series:
            hedged_peak = r.net_pnl if hedged_peak is None else max(hedged_peak, r.net_pnl)
            unhedged_peak = (
                r.benchmark_pnl if unhedged_peak is None else max(unhedged_peak, r.benchmark_pnl)
            )
            hedged_dd = hedged_peak - r.net_pnl
            unhedged_dd = unhedged_peak - r.benchmark_pnl
            hedged_max_dd = max(hedged_max_dd, hedged_dd)
            unhedged_max_dd = max(unhedged_max_dd, unhedged_dd)
            total_hedge_cost += r.hedge_cost

            points.append(
                {
                    "ts": r.ts.isoformat() if r.ts else None,
                    "cycle_id": r.cycle_id,
                    "hedged_pnl": float(r.net_pnl),
                    "unhedged_pnl": float(r.benchmark_pnl),
                    "hedge_cushion": float(r.net_pnl - r.benchmark_pnl),
                    "hedged_drawdown": float(hedged_dd),
                    "unhedged_drawdown": float(unhedged_dd),
                }
            )

        last = series[-1] if series else None
        return {
            "points": points,
            "hedged_max_drawdown": float(hedged_max_dd),
            "unhedged_max_drawdown": float(unhedged_max_dd),
            "drawdown_reduction": float(unhedged_max_dd - hedged_max_dd),
            "hedge_cushion": float(last.net_pnl - last.benchmark_pnl) if last else 0.0,
            "hedge_cost": float(total_hedge_cost),
            "is_cushioned": hedged_max_dd <= unhedged_max_dd,
        }

    def explain_dashboard_query(self) -> str:
        """Run EXPLAIN on the indexed dashboard query plan (P8-DB-3)."""
        with self._engine.connect() as conn:
            if conn.dialect.name == "sqlite":
                res = conn.execute(text("EXPLAIN QUERY PLAN SELECT * FROM performance WHERE cycle_id = 'c1' ORDER BY ts ASC"))
                return "\n".join(str(row) for row in res.fetchall())
            elif conn.dialect.name == "postgresql":
                res = conn.execute(text("EXPLAIN SELECT * FROM performance WHERE cycle_id = 'c1' ORDER BY ts ASC"))
                return "\n".join(str(row) for row in res.fetchall())
            return "OK"
