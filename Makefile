# Makefile — task P1-DB-2 wires the migration entrypoints; P1-BE-16 adds
# `openapi`. The full target set (dev, smoke, seed, db-reset, db-fresh,
# demo-restore) lands with P1-OPS-1.

ALEMBIC := python -m alembic -c backend/alembic.ini
PYTEST := python -m pytest

.PHONY: migrate migrate-down migrate-revision seed db-reset db-fresh test cov openapi

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

## seed: load canonical demo portfolio into the database
seed:
	python -m backend.seed

## db-reset: rollback to base, migrate to head, and seed canonical demo portfolio
db-reset:
	$(ALEMBIC) downgrade base
	$(ALEMBIC) upgrade head
	python -m backend.seed

## db-fresh: run clean drop, migrate, seed lifecycle
db-fresh: db-reset

## test: run the backend test suite (smoke tests excluded by default)
test:
	$(PYTEST) -q

## cov: run the test suite with a backend coverage report
cov:
	$(PYTEST) -q --cov=backend --cov-report=term-missing

## openapi: regenerate the checked-in openapi.json artifact for the frontend
openapi:
	python -m scripts.export_openapi

