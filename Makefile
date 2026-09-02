# Makefile — developer & CI entrypoints.
#
# P1-DB-2 wired the migration targets; P1-BE-16 added `openapi`; P1-OPS-1 fills
# in the rest of the target set this plan references (`dev`, `test`, `smoke`,
# `cov`, `migrate`, `seed`, `db-reset`, `db-fresh`, `openapi`, `demo-restore`);
# P1-OPS-2 adds `verify-phase-1` … `verify-phase-8`.
#
# Every target named anywhere in `docs/phased-implementation-plan.md` must exist
# here — `tests/ops/test_makefile.py` enforces that.

ALEMBIC := python -m alembic -c backend/alembic.ini
PYTEST  := python -m pytest

# `make dev` bind address — override on the command line, e.g. `make dev PORT=9000`.
HOST ?= 0.0.0.0
PORT ?= 8000

# `pytest` exits 5 when a selection collects no tests. For `verify-phase-N` on a
# phase whose suites do not exist yet that is a pass, not a failure — a real test
# failure still exits 1 and aborts the target.
PYTEST_OK_IF_EMPTY := || [ $$? -eq 5 ]

# Run a filtered slice of the frontend suite if the app has been scaffolded;
# otherwise say so and succeed. $(1) is a vitest name filter.
run-fe = @if [ -f frontend/package.json ]; then \
	  (cd frontend && npm test -- --run $(1)); \
	else \
	  echo "[verify] frontend not scaffolded (no frontend/package.json) -- skipping frontend tests"; \
	fi

# Echo a phase's acceptance checklist straight from the plan (single source of
# truth). $(1) is the phase number.
show-accept = @sed -n '/^\*\*Phase $(1) acceptance\*\*/,/^---$$/p' docs/phased-implementation-plan.md

.PHONY: help dev test smoke cov migrate migrate-down migrate-revision seed \
        db-reset db-fresh openapi demo-restore \
        verify-all verify-phase-1 verify-phase-2 verify-phase-3 verify-phase-4 \
        verify-phase-5 verify-phase-6 verify-phase-7 verify-phase-8

## help: list the documented targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'

# --- Run --------------------------------------------------------------------

## dev: boot the API with autoreload on :$(PORT)
dev:
	python -m uvicorn backend.api.app:app --reload --host $(HOST) --port $(PORT)

# --- Test -----------------------------------------------------------------

## test: run the backend suite (smoke tests excluded by default)
test:
	$(PYTEST) -q

## smoke: run only the smoke tests (needs real provider credentials)
smoke:
	$(PYTEST) -q -m smoke

## cov: run the suite with a backend coverage report
cov:
	$(PYTEST) -q --cov=backend --cov-report=term-missing

# --- Database ------------------------------------------------------------

## migrate: apply every migration up to head
migrate:
	$(ALEMBIC) upgrade head

## migrate-down: roll the database all the way back to base
migrate-down:
	$(ALEMBIC) downgrade base

## migrate-revision: scaffold a revision -- make migrate-revision m="add positions"
migrate-revision:
	$(ALEMBIC) revision -m "$(m)"

## seed: load the canonical demo portfolio into the database
seed:
	python -m backend.seed

## db-reset: downgrade to base, migrate to head, reseed
db-reset:
	$(ALEMBIC) downgrade base
	$(ALEMBIC) upgrade head
	python -m backend.seed

## db-fresh: clean drop -> migrate -> seed lifecycle (same as db-reset)
db-fresh: db-reset

## demo-restore: restore the canonical demo dataset (P8-DB-4 swaps in pg_dump/restore)
demo-restore: db-fresh

# --- Artifacts --------------------------------------------------------

## openapi: regenerate the checked-in openapi.json artifact for the frontend
openapi:
	python -m scripts.export_openapi

# --- Phase verification ------------------------------------------------
# Each `verify-phase-N` runs that phase's pytest selection + frontend subset,
# then prints the phase-acceptance block. A failing test aborts the target.

## verify-all: run verify-phase-1 through verify-phase-8 in order
verify-all: verify-phase-1 verify-phase-2 verify-phase-3 verify-phase-4 \
            verify-phase-5 verify-phase-6 verify-phase-7 verify-phase-8

## verify-phase-1: Foundation & contracts
verify-phase-1:
	@echo "== verify-phase-1 : Foundation & contracts =="
	$(PYTEST) -q tests/config tests/db tests/models tests/llm tests/integrations \
	  tests/api tests/ops tests/test_layout.py tests/test_env.py \
	  tests/test_contracts_roundtrip.py tests/test_fixtures.py $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"providers|routes|layout|client|sanity|App")
	$(call show-accept,1)

## verify-phase-2: Deterministic quant engine
verify-phase-2:
	@echo "== verify-phase-2 : Deterministic quant engine =="
	$(PYTEST) -q tests/quant $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"PayoffChart|Greeks")
	$(call show-accept,2)

## verify-phase-3: Analysis agents -> HedgeContext
verify-phase-3:
	@echo "== verify-phase-3 : Analysis agents -> HedgeContext =="
	$(PYTEST) -q tests/agents tests/api tests/e2e \
	  -k "context or analyz or portfolio_agent or stock or market or news or options_agent or assembler or readback" \
	  $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"PortfolioOverview|RiskOverview|AgentActivity")
	$(call show-accept,3)

## verify-phase-4: Strategy layer
verify-phase-4:
	@echo "== verify-phase-4 : Strategy layer =="
	$(PYTEST) -q tests/agents tests/api tests/e2e \
	  -k "hypothes or protective_put or put_spread or collar or no_hedge or prefilter or manager or strategy" \
	  $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"StrategyComparison|Recommendation|StrategyDetails|PayoffChart")
	$(call show-accept,4)

## verify-phase-5: Risk gate & execution
verify-phase-5:
	@echo "== verify-phase-5 : Risk gate & execution =="
	$(PYTEST) -q tests/agents tests/api tests/integrations tests/e2e \
	  -k "risk or execution or preflight or partial_fill or submit or exec_readback" \
	  $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"HedgeStatus|RiskChecklist|OrderStatus")
	$(call show-accept,5)

## verify-phase-6: Orchestrator & autonomous loop
verify-phase-6:
	@echo "== verify-phase-6 : Orchestrator & autonomous loop =="
	$(PYTEST) -q tests/agents tests/api tests/e2e \
	  -k "graph or node_ or routing or retry or failure_classifier or persist_hook or run_cycle or workflow or resume or full_cycle" \
	  $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"WorkflowState|AgentActivity|RunCycleButton")
	$(call show-accept,6)

## verify-phase-7: Monitoring & adaptive rebalancing
verify-phase-7:
	@echo "== verify-phase-7 : Monitoring & adaptive rebalancing =="
	$(PYTEST) -q tests/agents tests/api tests/e2e \
	  -k "monitor or trigger or deadband or cooldown or level2 or reassessment or apply_change or adaptation" \
	  $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"MonitoringPanel|HedgeDriftGauge|ReassessmentHistory|AdaptationStory")
	$(call show-accept,7)

## verify-phase-8: Dashboard, P&L & demo hardening
verify-phase-8:
	@echo "== verify-phase-8 : Dashboard, P&L & demo hardening =="
	$(PYTEST) -q tests/api tests/db tests/e2e \
	  -k "pnl or performance or observability or decision_trail or demo_replay or benchmark" \
	  $(PYTEST_OK_IF_EMPTY)
	$(call run-fe,"Performance|Dashboard|DecisionTrail|Configuration|TradeHistory")
	$(call show-accept,8)
