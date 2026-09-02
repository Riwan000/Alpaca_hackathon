"""baseline — establish Alembic's version table on a fresh database.

The real schema starts at P1-DB-3 (``portfolio_snapshots``). This revision
carries no DDL; it exists so ``alembic upgrade head`` creates
``alembic_version`` on an empty DB and ``alembic downgrade base`` unwinds
cleanly (task P1-DB-2).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-02

"""
from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema changes — baseline only."""


def downgrade() -> None:
    """No schema changes — baseline only."""
