# Makefile — task P1-DB-2 wires the migration entrypoints.
# The full target set (dev, test, smoke, cov, seed, db-reset, db-fresh,
# openapi, demo-restore) lands with P1-OPS-1.

ALEMBIC := python -m alembic -c backend/alembic.ini

.PHONY: migrate migrate-down migrate-revision

## migrate: apply every migration up to head
# Targets the Neon direct/unpooled DSN from .env, or $ALEMBIC_DATABASE_URL.
migrate:
	$(ALEMBIC) upgrade head

## migrate-down: roll the database all the way back to base
migrate-down:
	$(ALEMBIC) downgrade base

## migrate-revision: scaffold a revision -- make migrate-revision m="add positions"
migrate-revision:
	$(ALEMBIC) revision -m "$(m)"
