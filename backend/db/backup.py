"""Demo dataset backup and restore tooling — task P8-DB-4.

Exports database records into a portable JSON snapshot and restores them
into a fresh database instance for deterministic demo replay.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, delete, insert, select
from sqlalchemy.engine import Engine

_TABLES_TO_BACKUP = [
    "portfolio_snapshots",
    "positions",
    "agent_runs",
    "strategy_hypotheses",
    "strategy_decisions",
    "risk_checks",
    "orders",
    "fills",
    "monitoring_events",
    "performance",
    "workflow_state",
]


class _CustomEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, (decimal.Decimal, float)):
            return float(o)
        if isinstance(o, (_dt.datetime, _dt.date)):
            return o.isoformat()
        return super().default(o)


def export_demo_dataset(engine: Engine, output_path: Path | str) -> dict[str, int]:
    """Export all demo tables from ``engine`` to a JSON file. Returns row counts."""
    metadata = MetaData()
    metadata.reflect(bind=engine)
    data: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}

    with engine.connect() as conn:
        for table_name in _TABLES_TO_BACKUP:
            if table_name in metadata.tables:
                table = metadata.tables[table_name]
                rows = conn.execute(select(table)).mappings().all()
                data[table_name] = [dict(r) for r in rows]
                counts[table_name] = len(rows)
            else:
                data[table_name] = []
                counts[table_name] = 0

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, cls=_CustomEncoder, indent=2)

    return counts


import sqlalchemy as sa

def restore_demo_dataset(engine: Engine, backup_path: Path | str) -> dict[str, int]:
    """Restore dataset from JSON backup file into ``engine``. Returns inserted row counts."""
    path = Path(backup_path)
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, list[dict[str, Any]]] = json.load(f)

    metadata = MetaData()
    metadata.reflect(bind=engine)
    counts: dict[str, int] = {}

    with engine.begin() as conn:
        for table_name in reversed(_TABLES_TO_BACKUP):
            if table_name in metadata.tables:
                conn.execute(delete(metadata.tables[table_name]))

        for table_name in _TABLES_TO_BACKUP:
            if table_name in metadata.tables and data.get(table_name):
                table = metadata.tables[table_name]
                datetime_cols = {
                    c.name for c in table.columns
                    if isinstance(c.type, (sa.DateTime, sa.Date))
                }
                raw_rows = data[table_name]
                cleaned_rows = []
                for row in raw_rows:
                    cleaned_row = dict(row)
                    for col in datetime_cols:
                        val = cleaned_row.get(col)
                        if isinstance(val, str):
                            cleaned_row[col] = _dt.datetime.fromisoformat(val)
                    cleaned_rows.append(cleaned_row)

                if cleaned_rows:
                    conn.execute(insert(table), cleaned_rows)
                counts[table_name] = len(cleaned_rows)
            else:
                counts[table_name] = 0

    return counts

