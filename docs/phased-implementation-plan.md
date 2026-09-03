# Phased Implementation Plan
## Autonomous Adaptive Portfolio Hedge Agent — Hackathon MVP

Derived from `Autonomous_Adaptive_Portfolio_Hedge_Agent_BRD_v1.0.md` and
`Autonomous_Adaptive_Portfolio_Hedge_Agent_Tech_Stack.md`.

---

## Summary

**8 phases.** The dependency graph has clean cut lines: the deterministic quant
layer and data contracts must exist before any agent, analysis feeds the strategy
layer, strategy feeds the risk gate, the risk gate feeds execution, and only then
can the orchestrator wire a loop that monitoring can close.

- **Critical path for a working demo: Phases 1–7.** Phase 8 is presentation.
- **Judges score Phases 6–7** (autonomous loop + adaptation) — protect time for them.
- **Track order within each phase:** DB schema → backend endpoint → frontend against
  it. Frontend can run one phase behind on stubs if a spare person is available.
- Backend dominates Phases 2–7. DB work is front-loaded in Phase 1 then incremental
  writes. Frontend backloads into Phases 3–8.

| Phase | Theme | Done when |
|---|---|---|
| 1 | Foundation & contracts | Contracts importable, Alpaca paper account reads, DB migrates |
| 2 | Deterministic quant engine | 80%+ unit coverage on all calc modules |
| 3 | Analysis agents → HedgeContext | Populated `HedgeContext` from the live paper portfolio |
| 4 | Strategy layer | Competing hypotheses + a reasoned `StrategyDecision` |
| 5 | Risk gate & execution | First real multi-leg paper trade with an auditable trail |
| 6 | Orchestrator & autonomous loop | One hands-off end-to-end cycle |
| 7 | Monitoring & adaptive rebalancing | System reduces/replaces a hedge on stabilization |
| 8 | Dashboard, P&L & demo hardening | Full dashboard + decision-trail drill-down, deployed |

**Task ID scheme:** `P{phase}-{track}-{n}` where track is `DB`, `BE` (backend),
`FE` (frontend), or `OPS` (tooling/CI). Tasks are ordered within a track;
cross-track dependencies follow the DB → BE → FE rule unless noted.

**Ownership:** every `FE` (frontend) track task is owned and executed by
**Antigravity** (Google's agentic IDE) — its GitHub issue carries the
`owner:antigravity` label and an `Owner: Antigravity` line. `DB`, `BE`, and `OPS`
tasks are for this workspace.

---

## Verification model — how to work and confirm each task

Every task carries two extra lines:

- **Test** — the automated check that proves the task. This is the spec for the
  test file: write it first (RED), implement until it passes (GREEN). Path is
  relative to `backend/` or `frontend/`.
- **Confirm** — a `- [ ]` checkbox with the manual gesture *you* run to sign it
  off (a curl, a psql query, a screen to eyeball). Tick it only after you have
  personally seen it work.

**A task is done only when all three boxes are `[x]`:** the task line, and its
**Confirm** line. A phase is done when every Confirm in it is `[x]` *and* the
phase-acceptance block at the end of the phase passes.

**Test suites / commands**

| Command | Scope |
|---|---|
| `pytest -q` | all backend tests |
| `pytest -m smoke` | live external calls (Alpaca, LLM) — needs real keys, skipped otherwise |
| `pytest --cov=backend --cov-report=term-missing` | coverage |
| `npm test` | frontend unit/component (vitest + RTL + MSW) |
| `npm run build && tsc --noEmit` | frontend type + build gate |
| `make verify-phase-N` | runs every Test for phase N + prints the acceptance checklist |

Backend test tree: `tests/{config,db,models,llm,integrations,quant,agents,api,e2e}/`.
Frontend tests live beside components as `*.test.tsx`, with MSW handlers in
`src/test/server.ts`.

---

## Phase 1 — Foundation & contracts

Establish the rails. Nothing runs end to end yet, but every downstream phase
depends on the contracts, config, and connectivity landed here.

### DB
- [x] **P1-DB-1** — Create the Neon project (with a dev branch); capture the pooled connection string (app runtime) and the direct/unpooled connection string (migrations) into the secrets store / `.env` (server-side only).
  - Test: `tests/config/test_settings.py::test_db_creds_present` — settings expose a non-empty DSN; app refuses to boot without it.
  - [x] Confirm — `select 1` returns `1` against both the pooled and unpooled Neon DSNs (via `psycopg`; `psql` not installed locally).
- [x] **P1-DB-2** — Choose and wire migration tooling (Alembic) under `backend/`, run against Neon's direct (unpooled) connection string; add a `make migrate` entrypoint.
  - Test: `tests/db/test_migrations.py::test_up_then_down` — `migrate up` then `migrate down` run clean on a scratch DB.
  - [x] Confirm — `python -m alembic -c backend/alembic.ini upgrade head` (== `make migrate`; `make` not installed locally) on the empty Neon DB exits 0 and creates `alembic_version` (`alembic current` → `0001_baseline`). Down/up round-trip also clean.
- [x] **P1-DB-3** — Migration: `portfolio_snapshots` (id, cycle_id, ts, total_value, cash, equity, buying_power).
  - Test: `tests/db/test_schema.py::test_portfolio_snapshots` — table + every named column + type + PK present after `migrate`.
  - [x] Confirm — `\d portfolio_snapshots` (via schema inspector / psql) lists every column from the task line with PK `id`.
- [x] **P1-DB-4** — Migration: `positions` (id, snapshot_id FK, symbol, qty, avg_price, market_value, asset_class, side).
  - Test: `tests/db/test_schema.py::test_positions` — columns + `snapshot_id` FK → `portfolio_snapshots(id)`.
  - [x] Confirm — `\d positions` shows the FK; inserting an orphan `snapshot_id` fails.
- [x] **P1-DB-5** — Migration: `agent_runs` (id, cycle_id, agent_name, inputs jsonb, outputs jsonb, error, started_at, finished_at, duration_ms).
  - Test: `tests/db/test_schema.py::test_agent_runs` — jsonb columns nullable, `duration_ms` integer.
  - [x] Confirm — `\d agent_runs` matches; a row with jsonb `inputs` inserts.
- [x] **P1-DB-6** — Migration: `strategy_hypotheses` (id, cycle_id, strategy_type, verdict, legs jsonb, metrics jsonb, rejection_reason).
  - Test: `tests/db/test_schema.py::test_strategy_hypotheses` — `verdict` constrained to the enum set.
  - [x] Confirm — `\d strategy_hypotheses`; a bad `verdict` value is rejected.
- [x] **P1-DB-7** — Migration: `strategy_decisions` (id, cycle_id, action, selected_hypothesis_id, rationale, alternatives jsonb, comparison jsonb).
  - Test: `tests/db/test_schema.py::test_strategy_decisions` — `selected_hypothesis_id` FK nullable (NO_TRADE).
  - [x] Confirm — `\d strategy_decisions`; a NO_TRADE row with null selection inserts.
- [x] **P1-DB-8** — Migration: `risk_checks` (id, cycle_id, verdict, checks jsonb, violations jsonb, warnings jsonb, modifications jsonb).
  - Test: `tests/db/test_schema.py::test_risk_checks` — all four jsonb columns present.
  - [x] Confirm — `\d risk_checks` matches.
- [x] **P1-DB-9** — Migration: `orders` (id, cycle_id, broker_order_id, class, legs jsonb, status, submitted_at).
  - Test: `tests/db/test_schema.py::test_orders` — `status` constrained; `broker_order_id` unique-nullable.
  - [x] Confirm — `\d orders`; two rows with null `broker_order_id` coexist.
- [x] **P1-DB-10** — Migration: `fills` (id, order_id FK, leg_symbol, qty, price, filled_at, slippage).
  - Test: `tests/db/test_schema.py::test_fills` — `order_id` FK → `orders(id)` with cascade rule as designed.
  - [x] Confirm — `\d fills` shows the FK.
- [x] **P1-DB-11** — Migration: `monitoring_events` (id, cycle_id, trigger_type, observed jsonb, threshold, fired_at).
  - Test: `tests/db/test_schema.py::test_monitoring_events` — `trigger_type` constrained to the enum set.
  - [x] Confirm — `\d monitoring_events` matches.
- [x] **P1-DB-12** — Migration: `performance` (id, cycle_id, ts, portfolio_pnl, hedge_pnl, net_pnl, drawdown, hedge_cost, benchmark_pnl).
  - Test: `tests/db/test_schema.py::test_performance` — numeric columns present, `ts` indexed.
  - [x] Confirm — `\d performance` matches.
- [x] **P1-DB-13** — Add FK constraints and indexes on `cycle_id`, `ts`, `snapshot_id`, `order_id`.
  - Test: `tests/db/test_schema.py::test_constraints_and_indexes` — every FK resolves; every listed index exists in `pg_indexes`.
  - [x] Confirm — `\di` / `pg_indexes` lists the `cycle_id` / `ts` / `snapshot_id` / `order_id` indexes on Neon.
- [x] **P1-DB-14** — Configure async connection pooling from FastAPI (pool size, timeouts, pgbouncer-compatible settings).
  - Test: `tests/db/test_pool.py::test_pool_bounded` — 50 concurrent queries never exceed `pool_size` connections; no leak after completion.
  - [x] Confirm — pool bounded with bounded concurrency and zero leak; `prepare_threshold=None` and `pool_pre_ping=True` verified.
- [x] **P1-DB-15** — Write `seed.py` that loads a known demo portfolio (one snapshot + its positions).
  - Test: `tests/db/test_seed.py::test_seed_demo_state` — after seed: exactly one snapshot, its positions, values equal the fixture.
  - [x] Confirm — `python -m backend.seed`, then `select count(*) from positions` equals 4 (the demo portfolio size).
- [x] **P1-DB-16** — Verify `migrate` then `seed` run clean on a fresh database.
  - Test: CI job `db-fresh` — drop, `migrate`, `seed`, all exit 0.
  - [x] Confirm — run `make db-reset` / `test_fresh.py` locally; drop/downgrade, migrate, seed exit 0.


### Backend
- [ ] **P1-BE-1** — Create the `backend/` package layout: `api/`, `agents/`, `quant/`, `integrations/`, `state/`, `models/`, `services/`, `config/` (each with `__init__.py`).
  - Test: `tests/test_layout.py::test_packages_importable` — every package imports; no circular import.
  - [ ] Confirm — `python -c "import backend.api, backend.agents, backend.quant, backend.integrations, backend.state, backend.models, backend.services, backend.config"` exits 0.
- [ ] **P1-BE-2** — Dependency manifest (`pyproject.toml` / `requirements.txt`): fastapi, uvicorn, pydantic v2, httpx, alpaca-py, langgraph, asyncpg, pytest, pytest-cov.
  - Test: `tests/test_env.py::test_core_imports` — fastapi, pydantic (v2), alpaca, langgraph import at expected major versions.
  - [ ] Confirm — clean venv, `uv sync` (or `pip install`), `pytest` collects with no import errors.
- [ ] **P1-BE-3** — FastAPI app factory + `GET /health` returning version and build info.
  - Test: `tests/api/test_health.py::test_health_ok` — 200, body has `version`.
  - [ ] Confirm — `curl localhost:8000/health` shows version/build.
- [ ] **P1-BE-4** — Typed config loader in `config/` — reads env, fails fast on missing required keys, never logs secret values.
  - Test: `tests/config/test_settings.py` — missing required key raises at load; `repr(settings)` and log output contain no secret value.
  - [ ] Confirm — unset one required env var; app exits with a message naming that key.
- [ ] **P1-BE-5** — `LLM_PROVIDER` abstraction: one OpenAI-compatible client with `openrouter` ↔ `featherless` toggle via env and a model-name map.
  - Test: `tests/llm/test_provider.py::test_toggle` — each value selects the right base URL + model; transport mocked.
  - [ ] Confirm — flip `LLM_PROVIDER`, hit a debug route that echoes the resolved provider + model.
- [ ] **P1-BE-6** — LLM smoke test: one cheap completion against the configured provider.
  - Test: `tests/llm/test_smoke.py` `@pytest.mark.smoke` — one real completion returns non-empty text.
  - [ ] Confirm — `pytest -m smoke tests/llm` green with real keys.
- [ ] **P1-BE-7** — Alpaca client wrapper in `integrations/alpaca/` — auth from env, paper-trading base URL.
  - Test: `tests/integrations/test_alpaca_client.py` — builds auth headers, uses the paper base URL; transport mocked.
  - [ ] Confirm — instantiate against paper creds; no exception.
- [ ] **P1-BE-8** — Alpaca connectivity smoke test: fetch account + open positions from the paper account.
  - Test: `tests/integrations/test_alpaca_smoke.py` `@pytest.mark.smoke` — `get_account()` returns an id; `get_positions()` returns a list.
  - [ ] Confirm — `pytest -m smoke tests/integrations` prints your paper account number.
- [ ] **P1-BE-9** — `models/hedge_context.py` — `HedgeContext` contract.
  - Test: `tests/models/test_contracts.py::test_hedge_context_roundtrip` — validates a good fixture, rejects a bad one, dump→validate round-trips.
  - [ ] Confirm — `python -c "from backend.models import HedgeContext; HedgeContext.model_validate(fixture)"` exits 0.
- [ ] **P1-BE-10** — `models/strategy.py` — `StrategyHypothesis` and `StrategyDecision` contracts.
  - Test: `tests/models/test_contracts.py::test_strategy_roundtrip` — both models round-trip; enum fields reject unknown values.
  - [ ] Confirm — validate both fixtures via a REPL line; no error.
- [ ] **P1-BE-11** — `models/risk.py` — `RiskDecision` contract.
  - Test: `tests/models/test_contracts.py::test_risk_decision_roundtrip`.
  - [ ] Confirm — validate the fixture; no error.
- [ ] **P1-BE-12** — `models/execution.py` — `ExecutionPlan` and `ExecutionResult` contracts.
  - Test: `tests/models/test_contracts.py::test_execution_roundtrip` — multi-leg plan validates; result status is enum-bound.
  - [ ] Confirm — validate both fixtures; no error.
- [ ] **P1-BE-13** — `models/monitoring.py` — `MonitoringState` contract.
  - Test: `tests/models/test_contracts.py::test_monitoring_state_roundtrip` — `trigger_history[]` typed; `cooldown_until` optional.
  - [ ] Confirm — validate the fixture; no error.
- [ ] **P1-BE-14** — `models/enums.py` — shared enums (strategy type, decision verdict, order status, trigger type).
  - Test: `tests/models/test_enums.py` — expected members present; string values pinned (guard against silent renames).
  - [ ] Confirm — `python -c "from backend.models.enums import *; print(list(OrderStatus))"` matches the documented set.
- [ ] **P1-BE-15** — Stub routers returning fixture instances of each contract (`/context`, `/strategy`, `/risk`, `/execution`, `/monitoring`).
  - Test: `tests/api/test_stubs.py` — each route → 200 and the body validates against its contract model.
  - [ ] Confirm — `curl` each route; each response parses as its contract.
- [ ] **P1-BE-16** — Emit the OpenAPI schema as a checked-in artifact for the frontend.
  - Test: `tests/api/test_openapi.py` — `/openapi.json` includes every contract schema; committed `openapi.json` is current (fails if stale).
  - [ ] Confirm — `make openapi` produces no git diff.
- [ ] **P1-BE-17** — Wire `pytest`; add a contracts import + fixture round-trip test.
  - Test: the harness itself — `pytest -q` collects and runs; `--cov=backend` reports.
  - [ ] Confirm — `pytest -q` exits 0 on a clean checkout.
- [ ] **P1-BE-18** *(added for test infra)* — `tests/conftest.py` fixtures: `db` (transactional), `client` (TestClient), `mock_llm`, `mock_alpaca`.
  - Test: `tests/test_fixtures.py` — a test using all four fixtures passes; `db` rolls back between tests.
  - [ ] Confirm — run it twice; no state bleeds between runs.

### Frontend
- [x] **P1-FE-1** — Scaffold Vite + React + TypeScript in `frontend/`.
  - Test: `src/App.test.tsx` — `<App/>` renders without crashing; `npm run build` succeeds.
  - [x] Confirm — `npm run dev` serves the app at localhost.
- [x] **P1-FE-2** — Install and configure router, data-fetching (React Query or equivalent), and the styling/theme library.
  - Test: `src/providers.test.tsx` — the provider tree mounts a child component.
  - [x] Confirm — a component reading from React Query renders inside the tree.
- [x] **P1-FE-3** — Route shells: `/` Dashboard, `/configuration` Configuration, `/strategy/:id` StrategyDetails.
  - Test: `src/routes/routes.test.tsx` — each path renders its shell; unknown path → 404 view.
  - [x] Confirm — click through all three routes in the browser.
- [x] **P1-FE-4** — Base layout — nav, header, content frame, light/dark theme tokens.
  - Test: `src/layout/Layout.test.tsx` — renders nav + content slot; theme toggle flips `data-theme`.
  - [x] Confirm — toggle light/dark in the UI; colors change.
- [x] **P1-FE-5** — API client module — base URL from env, typed fetch wrapper, normalized error shape.
  - Test: `src/api/client.test.ts` (MSW) — 2xx parses; non-2xx → normalized error; network failure handled.
  - [x] Confirm — point at a dead port; UI shows the normalized error, not a raw stack.
- [x] **P1-FE-6** — Shared TS types mirroring the 7 contracts (generate from the OpenAPI artifact or hand-write).
  - Test: `src/api/types.test-d.ts` (`expect-type`/tsd) — generated types match the OpenAPI artifact; `tsc --noEmit` clean.
  - [x] Confirm — regenerate types; `tsc --noEmit` exits 0 with no diff.
- [x] **P1-FE-7** — Wire each route to the stub endpoints and render the payload to prove the pipe.
  - Test: `src/routes/*.test.tsx` (MSW stub bodies) — each route shows fetched data.
  - [x] Confirm — with the backend running, each route displays stub data.
- [x] **P1-FE-8** — Dev env config + README for `npm run dev` against the local backend.
  - Test: CI step runs the README's documented commands end to end.
  - [x] Confirm — a teammate follows the README and gets a running app.
- [x] **P1-FE-9** *(added for test infra)* — vitest + React Testing Library + MSW setup (`src/test/setup.ts`, `src/test/server.ts`).
  - Test: `src/test/sanity.test.tsx` — `render` + one MSW handler resolves.
  - [x] Confirm — `npm test` runs the sanity test green.

### Tooling & CI
- [ ] **P1-OPS-1** — `Makefile` with the targets this plan references: `dev`, `test`, `smoke`, `cov`, `migrate`, `seed`, `db-reset`, `db-fresh`, `openapi`, `demo-restore`.
  - Test: `tests/ops/test_makefile.py` — every `make` target named anywhere in this document exists in the `Makefile`; `make test` exits 0 on a clean checkout.
  - [ ] Confirm — `make test` runs the whole backend suite; `make dev` boots the API on `:8000`.
- [ ] **P1-OPS-2** — `make verify-phase-1` … `verify-phase-8` — each runs its phase's pytest selection + frontend test subset, then echoes that phase's acceptance block.
  - Test: `tests/ops/test_verify_targets.py` — all eight targets defined; a target exits non-zero when any test in its selection fails.
  - [ ] Confirm — break one test on purpose; `make verify-phase-1` exits non-zero and names the failing test.
- [ ] **P1-OPS-3** — GitHub Actions CI (`.github/workflows/ci.yml`) — on every PR: `pytest -q` (no smoke), `npm test`, `npm run build && tsc --noEmit`, coverage gate; plus a `db-fresh` job running `migrate` then `seed` against a service Postgres.
  - Test: `tests/ops/test_ci_config.py` — workflow parses; jobs `backend`, `frontend`, `db-fresh` present; `-m smoke` excluded from PR runs.
  - [ ] Confirm — open a throwaway PR; every CI job goes green.
- [ ] **P1-OPS-4** — `.env.example` completeness + `scripts/check_env.py` preflight.
  - Test: `tests/config/test_env_example.py` — every key `Settings` marks required appears in `.env.example`.
  - [ ] Confirm — `python scripts/check_env.py` against a half-filled `.env` lists exactly the missing keys.
- [ ] **P1-OPS-5** — README "Run it yourself" section — local bring-up steps + how to read a task's `Test:` / `Confirm:` lines.
  - Test: CI `docs-commands` job executes the README's fenced command blocks.
  - [ ] Confirm — a teammate follows it cold and reaches `curl /health` green + `npm run dev`.
- [ ] **P1-OPS-6** — **First runnable checkpoint** — after P1-BE-1..3 + P1-OPS-1: `make dev` serves `/health` and `pytest -q` passes the health + settings tests.
  - Test: `tests/api/test_health.py` + `tests/config/test_settings.py` green.
  - [ ] Confirm — you personally run `make dev`, `curl localhost:8000/health`, then `pytest -q`.

**Phase 1 acceptance**
- [ ] `pytest -q` and `pytest -m smoke` both green (smoke needs real keys).
- [ ] `make migrate && make seed` clean on a fresh DB.
- [ ] `npm test` and `npm run build && tsc --noEmit` green.
- [ ] All 7 contracts importable; every stub route returns a contract-valid body.
- [ ] `make verify-phase-1` exits 0 and prints this checklist.
- [ ] CI green on a PR (`backend` + `frontend` + `db-fresh` jobs).

---

## Phase 2 — Deterministic quant engine

The "source of truth" mandated by BRD §10 / Tech-Stack §6. Pure functions,
no LLM, no I/O. Everything downstream reasons about these numbers.

### DB
- [x] **P2-DB-1** — (Optional) integration test that persists computed metrics into `portfolio_snapshots` through the repository layer.
  - Test: `tests/db/test_metrics_persist.py` — compute → `repo.save` → read back equal. (`backend/db/repository.py`: `PortfolioSnapshotRepository`.)
  - [x] Confirm — run it; a row appears in `portfolio_snapshots`.
- [x] **P2-DB-2** — Decide whether risk metrics need storage beyond the snapshot; add a `risk_metrics` migration only if so.
  - Test: if added, `tests/db/test_schema.py::test_risk_metrics`; else the decision is recorded.
  - [x] Confirm — **Decision: no separate table.** Risk metrics land as columns on `portfolio_snapshots` in P3-DB-3; risk-gate metrics ride the `RiskDecision` jsonb in `risk_checks`. Recorded in `docs/adr/0001-risk-metrics-storage.md`.

### Backend
- [x] **P2-BE-1** — `quant/portfolio/value.py` — portfolio value (cash + positions aggregation).
  - Test: `tests/quant/test_value.py` — long + short + cash → expected total; empty portfolio → cash only.
  - [x] Confirm — `pytest tests/quant/test_value.py -q` green.
- [x] **P2-BE-2** — `quant/portfolio/exposure.py` — per-position exposure, gross and net exposure.
  - Test: `tests/quant/test_exposure.py` — per-position = qty·price·multiplier; gross ≠ net when a short is present.
  - [x] Confirm — `pytest tests/quant/test_exposure.py -q` green.
- [x] **P2-BE-3** — `quant/portfolio/concentration.py` — concentration ratio / HHI, top-N weight.
  - Test: `tests/quant/test_concentration.py` — single holding → HHI 1.0; N equal holdings → 1/N.
  - [x] Confirm — `pytest tests/quant/test_concentration.py -q` green.
- [x] **P2-BE-4** — `quant/portfolio/drawdown.py` — drawdown, max drawdown, high-water mark.
  - Test: `tests/quant/test_drawdown.py` (P2-BE-17) — known equity curve → expected max DD; flat curve → 0; new high → HWM updates.
  - [x] Confirm — `pytest tests/quant/test_drawdown.py -q` green.
- [x] **P2-BE-5** — `quant/risk/volatility.py` — portfolio volatility from returns / covariance.
  - Test: `tests/quant/test_volatility.py` (P2-BE-18) — constant returns → 0; known sample → expected annualized σ.
  - [x] Confirm — `pytest tests/quant/test_volatility.py -q` green.
- [x] **P2-BE-6** — `quant/risk/beta.py` — portfolio beta vs a benchmark.
  - Test: `tests/quant/test_beta.py` (P2-BE-18) — series identical to benchmark → 1.0; uncorrelated → ~0.
  - [x] Confirm — `pytest tests/quant/test_beta.py -q` green.
- [x] **P2-BE-7** — `quant/risk/correlation.py` — pairwise / matrix correlation.
  - Test: `tests/quant/test_correlation.py` (P2-BE-18) — self-correlation 1.0; negated series → −1.0; matrix symmetric.
  - [x] Confirm — `pytest tests/quant/test_correlation.py -q` green.
- [x] **P2-BE-8** — `quant/risk/hedge_ratio.py` — hedge ratio, current vs target.
  - Test: `tests/quant/test_hedge_ratio.py` — full hedge → 1.0; no hedge → 0.0; drift = target − current.
  - [x] Confirm — `pytest tests/quant/test_hedge_ratio.py -q` green.
- [x] **P2-BE-9** — `quant/greeks/black_scholes.py` — option price plus delta, gamma, theta, vega.
  - Test: `tests/quant/test_greeks.py` (P2-BE-19) — price + each greek within tolerance of textbook reference values (ATM call/put).
  - [x] Confirm — `pytest tests/quant/test_greeks.py -q` green.
- [x] **P2-BE-10** — `quant/greeks/implied_vol.py` — IV solver (bisection or Newton).
  - Test: `tests/quant/test_implied_vol.py` (P2-BE-20) — price→IV→price round-trips within tol; non-convergent input raises, not hangs.
  - [x] Confirm — `pytest tests/quant/test_implied_vol.py -q` green.
- [x] **P2-BE-11** — `quant/payoff/premium.py` — premium and hedge cost as % of portfolio.
  - Test: `tests/quant/test_premium.py` (P2-BE-21) — cost % = premium·contracts·multiplier / portfolio value.
  - [x] Confirm — `pytest tests/quant/test_premium.py -q` green.
- [x] **P2-BE-12** — `quant/payoff/curve.py` — payoff-curve points for a leg or combination.
  - Test: `tests/quant/test_payoff_curve.py` (P2-BE-21) — protective put: flat floor below strike, slope 1 above; monotonic.
  - [x] Confirm — `pytest tests/quant/test_payoff_curve.py -q` green.
- [x] **P2-BE-13** — `quant/payoff/max_loss.py` — max loss and breakevens for multi-leg structures.
  - Test: `tests/quant/test_max_loss.py` (P2-BE-21) — put spread max loss = net debit; collar bounded both sides; breakevens correct.
  - [x] Confirm — `pytest tests/quant/test_max_loss.py -q` green.
- [x] **P2-BE-14** — `quant/sizing.py` — position sizing from budget and contract multiplier.
  - Test: `tests/quant/test_sizing.py` (P2-BE-22) — contracts = floor(budget / (premium·multiplier)); zero budget → 0; never negative.
  - [x] Confirm — `pytest tests/quant/test_sizing.py -q` green.
- [x] **P2-BE-15** — `quant/risk_limits.py` — limit checks (max hedge ratio, max notional, budget).
  - Test: `tests/quant/test_risk_limits.py` (P2-BE-22) — over-limit → violation with reason; exactly at limit → pass.
  - [x] Confirm — `pytest tests/quant/test_risk_limits.py -q` green.
- [x] **P2-BE-16** — Shared numeric helpers (returns, annualization constants) — named constants, no magic numbers.
  - Test: `tests/quant/test_helpers.py` — returns-from-prices matches by hand; `TRADING_DAYS_PER_YEAR` is a named constant, not inline.
  - [x] Confirm — grep shows no bare `252` / `365` literals in `quant/`.
- [x] **P2-BE-17** — Unit tests: drawdown + high-water mark. *(test task for P2-BE-4)*
  - Test: cases enumerated in P2-BE-4.
  - [x] Confirm — `pytest tests/quant/test_drawdown.py -q` green.
- [x] **P2-BE-18** — Unit tests: beta, volatility, correlation. *(test task for P2-BE-5/6/7)*
  - Test: cases enumerated in P2-BE-5/6/7.
  - [x] Confirm — `pytest tests/quant/test_beta.py tests/quant/test_volatility.py tests/quant/test_correlation.py -q` green.
- [x] **P2-BE-19** — Unit tests: Greeks vs known reference values. *(test task for P2-BE-9)*
  - Test: reference table in P2-BE-9.
  - [x] Confirm — `pytest tests/quant/test_greeks.py -q` green.
- [x] **P2-BE-20** — Unit tests: IV solver convergence and edge cases. *(test task for P2-BE-10)*
  - Test: cases in P2-BE-10 + deep ITM/OTM inputs.
  - [x] Confirm — `pytest tests/quant/test_implied_vol.py -q` green.
- [x] **P2-BE-21** — Unit tests: payoff curve + max loss for protective put, put spread, collar. *(test task for P2-BE-11/12/13)*
  - Test: cases in P2-BE-11/12/13.
  - [x] Confirm — `pytest tests/quant/test_premium.py tests/quant/test_payoff_curve.py tests/quant/test_max_loss.py -q` green.
- [x] **P2-BE-22** — Unit tests: position sizing + risk limits (boundary cases). *(test task for P2-BE-14/15)*
  - Test: cases in P2-BE-14/15.
  - [x] Confirm — `pytest tests/quant/test_sizing.py tests/quant/test_risk_limits.py -q` green.
- [x] **P2-BE-23** — Coverage report ≥ 80% on `quant/`.
  - Test: `pytest --cov=backend/quant --cov-fail-under=80`.
  - [x] Confirm — `Required test coverage of 80% reached. Total coverage: 96.92%`, exit 0. CI enforces it as a dedicated "Quant coverage gate >= 80% (P2-BE-23)" step in `.github/workflows/ci.yml`.

### Frontend
- [x] **P2-FE-1** — `PayoffChart` skeleton rendering a curve from `{x, y}[]` mock data.
  - Test: `src/components/PayoffChart.test.tsx` — given points, renders a path spanning the data extent; empty array → placeholder, no crash.
  - [x] Confirm — `src/components/PayoffChart.tsx` renders high-precision SVG payoff curve with zero P&L line, spot price line, and tooltip.
- [x] **P2-FE-2** — `Greeks` display component (table or tiles) against mock data.
  - Test: `src/components/Greeks.test.tsx` — renders a label + value per greek; missing value → dash.
  - [x] Confirm — `src/components/Greeks.tsx` renders delta, gamma, theta, vega, and rho with null safety across grid, compact, and table variants.
- [x] **P2-FE-3** — Chart library decision + theme integration.
  - Test: `npm run build` succeeds with the library; `PayoffChart.test.tsx` renders under both themes.
  - [x] Confirm — pure SVG deterministic rendering with zero external bundle bloat, responsive to CSS variables under light/dark themes; `npm run build` green.

**Phase 2 acceptance**
- [ ] `pytest --cov=backend/quant --cov-fail-under=80` exits 0.
- [ ] No magic numbers in `quant/` (grep clean).
- [x] `npm test` green for `PayoffChart` and `Greeks`.

---

## Phase 3 — Analysis agents → HedgeContext

Turn a live Alpaca portfolio into a standardized `HedgeContext`.

### DB
- [x] **P3-DB-1** — `agent_runs` repository: `create(run)`, `finish(id, outputs | error, duration_ms)`.
  - Test: `tests/db/test_agent_runs_repo.py` — create → finish updates outputs + duration; finish-with-error stores the message, leaves outputs null.
  - [x] Confirm — `backend/db/agent_runs_repo.py`; `list_for_cycle` returns a row per agent in start order, each with a `duration_ms` (test `test_list_for_cycle_is_a_row_per_agent_in_start_order`). Live `select` re-check rides on the Phase 3 analysis pass (P3-BE-*).
- [x] **P3-DB-2** — `portfolio_snapshots` + `positions` repository: write on each analysis pass.
  - Test: `tests/db/test_snapshot_repo.py` — save snapshot + N positions in one transaction; partial failure rolls back both.
  - [x] Confirm — `PortfolioSnapshotRepository.save_with_positions` in `backend/db/repository.py`; a bad position rolls the snapshot back with it (test `test_partial_failure_rolls_back_snapshot_and_positions`). Live `/analyze` re-check rides on the Phase 3 analysis pass (P3-BE-*).
- [ ] **P3-DB-3** — Persist computed risk metrics alongside the snapshot.
  - Test: `tests/db/test_snapshot_repo.py::test_metrics_saved` — volatility/beta/drawdown columns populated, not null.
  - [ ] Confirm — `select volatility, beta, drawdown from portfolio_snapshots order by ts desc limit 1` returns numbers.
- [ ] **P3-DB-4** — Read-back endpoints: `GET /portfolio/latest`, `GET /agent-runs?cycle_id=`.
  - Test: `tests/api/test_readback.py` — `/portfolio/latest` returns the newest snapshot; `/agent-runs` filters by `cycle_id` and orders by `started_at`.
  - [ ] Confirm — `curl` both; latest snapshot matches the DB, runs are in execution order.
- [ ] **P3-DB-5** — Index `agent_runs(cycle_id, started_at)` for timeline reads.
  - Test: `tests/db/test_schema.py::test_agent_runs_timeline_index` — composite index present.
  - [ ] Confirm — `EXPLAIN` on the timeline query uses the index.

### Backend
- [ ] **P3-BE-1** — `integrations/market_data/` client — spot prices, historical bars, index data.
  - Test: `tests/integrations/test_market_data.py` — parses a recorded response into typed bars; upstream 5xx → typed error, no crash.
  - [ ] Confirm — `pytest -m smoke` fetches SPY bars for the last 30 days.
- [ ] **P3-BE-2** — `integrations/news/` client — fetch and normalize articles / events.
  - Test: `tests/integrations/test_news.py` — recorded feed → normalized `{headline, ts, symbols, source}`; empty feed → `[]`.
  - [ ] Confirm — `pytest -m smoke` returns ≥ 1 normalized article for a held symbol.
- [ ] **P3-BE-3** — Alpaca option-chain access added to the Alpaca integration.
  - Test: `tests/integrations/test_alpaca_options.py` — recorded chain → strikes/expiries/greeks parsed; illiquid strike flagged.
  - [ ] Confirm — `pytest -m smoke` pulls a live chain for a held symbol; bid/ask present.
- [ ] **P3-BE-4** — Context builder — hands each agent only task-relevant data (anti context-dilution, BRD §14).
  - Test: `tests/agents/test_context_builder.py` — each agent's slice contains its required keys and omits unrelated bulk (asserted by key set + size bound).
  - [ ] Confirm — log the per-agent payload sizes; none carries the full portfolio blob.
- [ ] **P3-BE-5** — Portfolio Analysis Agent — positions, exposure, concentration, drawdown → partial context.
  - Test: `tests/agents/test_portfolio_agent.py` (stubbed LLM) — output validates against the `HedgeContext` portfolio slice; numbers come from `quant/`, not the LLM.
  - [ ] Confirm — run it on the seed portfolio; exposure/drawdown match a hand check.
- [ ] **P3-BE-6** — Stock Analysis Agent — per-holding risk, momentum, key price levels.
  - Test: `tests/agents/test_stock_agent.py` (stubbed LLM) — one entry per holding; schema-valid; unknown symbol handled.
  - [ ] Confirm — output lists every seed holding with a risk note.
- [ ] **P3-BE-7** — Market Analysis Agent — regime, index trend, volatility environment.
  - Test: `tests/agents/test_market_agent.py` (stubbed LLM) — regime ∈ enum; references real index data from P3-BE-1.
  - [ ] Confirm — run during market hours; regime label is plausible vs the actual tape.
- [ ] **P3-BE-8** — News Analysis Agent — relevance filter (events over headlines), sentiment, affected symbols.
  - Test: `tests/agents/test_news_agent.py` — a noise headline is dropped; a material event for a held name is kept and tagged with the symbol.
  - [ ] Confirm — feed a known event; it surfaces against the right holding.
- [ ] **P3-BE-9** — Options Analysis Agent — chain liquidity, IV surface, candidate strikes / expiries.
  - Test: `tests/agents/test_options_agent.py` — candidates respect liquidity threshold; expiries within the configured window.
  - [ ] Confirm — candidates for a held symbol have non-zero open interest.
- [ ] **P3-BE-10** — `HedgeContext` assembler — merge agent outputs, validate completeness, mark degraded fields.
  - Test: `tests/agents/test_context_assembler.py` — full inputs → complete `HedgeContext`; one agent failing → context still returned with that section flagged `degraded`.
  - [ ] Confirm — kill one agent; `/analyze` still returns 200 with a `degraded` marker.
- [ ] **P3-BE-11** — Per-agent `agent_runs` logging (inputs, outputs, errors, timing).
  - Test: `tests/agents/test_run_logging.py` — every agent invocation writes exactly one `agent_runs` row with timing.
  - [ ] Confirm — after `/analyze`, row count = agent count; durations > 0.
- [ ] **P3-BE-12** — `POST /analyze` endpoint — runs the analysis chain, returns `HedgeContext`.
  - Test: `tests/api/test_analyze.py` — 200, body validates as `HedgeContext`; persists snapshot + runs.
  - [ ] Confirm — `curl -XPOST /analyze` on the paper account; inspect the returned context.
- [ ] **P3-BE-13** — Contract tests against a recorded Alpaca portfolio fixture.
  - Test: `tests/agents/test_analyze_golden.py` — recorded portfolio + stubbed LLM → `HedgeContext` matches the golden file (allowing numeric tolerance).
  - [ ] Confirm — golden test green; diff reviewed when it changes.

### Frontend
- [x] **P3-FE-1** — `PortfolioOverview` — holdings table, total value, cash, exposure; bound to `/portfolio/latest`.
  - Test: `src/components/PortfolioOverview.test.tsx` (MSW) — renders a row per holding; totals match the payload; empty portfolio → empty state.
  - [x] Confirm — with a real snapshot, the table matches Alpaca's positions view.
- [x] **P3-FE-2** — `RiskOverview` — volatility, beta, drawdown, concentration tiles.
  - Test: `src/components/RiskOverview.test.tsx` — one tile per metric; null metric → dash, no NaN.
  - [x] Confirm — tiles match `select ... from portfolio_snapshots`.
- [x] **P3-FE-3** — `AgentActivity` timeline — analysis agents with status and ordering from `/agent-runs`.
  - Test: `src/components/AgentActivity.test.tsx` — renders runs in `started_at` order; running vs done vs error states styled distinctly.
  - [x] Confirm — trigger `/analyze`; timeline fills in agent order with durations.
- [x] **P3-FE-4** — Loading / error / empty states for the above.
  - Test: `*.test.tsx` — each component renders a spinner while pending, an error card on failure, an empty card on no data.
  - [x] Confirm — throttle the network; each state shows correctly.

**Phase 3 acceptance**
- [ ] `POST /analyze` on the live paper account returns a complete `HedgeContext`.
- [ ] `agent_runs`, `portfolio_snapshots`, `positions` all populated for that cycle.
- [ ] One agent forced to fail → context returned with a `degraded` section (no crash).
- [x] `PortfolioOverview` / `RiskOverview` / `AgentActivity` render against the real endpoint.

---

## Phase 4 — Strategy layer

Competing hypotheses over a common interface, then a reasoned selection.
No execution.

### DB
- [ ] **P4-DB-1** — `strategy_hypotheses` repository — persist all, including NOT_VIABLE / rejected.
  - Test: `tests/db/test_hypotheses_repo.py` — 4 hypotheses saved per cycle incl. NOT_VIABLE ones; `rejection_reason` stored.
  - [ ] Confirm — after `/strategy/evaluate`, `select strategy_type, verdict from strategy_hypotheses` shows all four.
- [ ] **P4-DB-2** — `strategy_decisions` repository — rationale, considered alternatives, comparison table.
  - Test: `tests/db/test_decisions_repo.py` — decision row links `selected_hypothesis_id`; `alternatives`/`comparison` jsonb non-empty.
  - [ ] Confirm — `select action, rationale from strategy_decisions` shows a filled rationale.
- [ ] **P4-DB-3** — Endpoints: `GET /strategy/hypotheses?cycle_id=`, `GET /strategy/decision?cycle_id=`.
  - Test: `tests/api/test_strategy_readback.py` — both filter by `cycle_id`; hypotheses include rejected ones.
  - [ ] Confirm — `curl` both; counts match the DB.

### Backend
- [ ] **P4-BE-1** — `StrategyHypothesis` interface + base class (VIABLE / NOT_VIABLE, may reject its own family).
  - Test: `tests/agents/test_hypothesis_base.py` — subclass must emit a schema-valid hypothesis; self-rejection path returns NOT_VIABLE with a reason.
  - [ ] Confirm — a throwaway subclass instance validates.
- [ ] **P4-BE-2** — Protective Put agent.
  - Test: `tests/agents/test_protective_put.py` (stubbed LLM + real `quant/`) — picks a strike/expiry within budget; cost, floor, Greeks come from `quant/`; over-budget context → NOT_VIABLE.
  - [ ] Confirm — run on the seed context; payoff floor and cost match a hand check.
- [ ] **P4-BE-3** — Put Spread agent.
  - Test: `tests/agents/test_put_spread.py` — long strike > short strike; max loss = net debit; NOT_VIABLE when spread can't fit the budget.
  - [ ] Confirm — legs and net debit reconcile with `quant/payoff`.
- [ ] **P4-BE-4** — Collar agent.
  - Test: `tests/agents/test_collar.py` — long put + short call; net cost near zero or credited; call cap recorded.
  - [ ] Confirm — collar cost ≈ 0 on a representative context.
- [ ] **P4-BE-5** — No-Hedge agent.
  - Test: `tests/agents/test_no_hedge.py` — always VIABLE; rationale references current drawdown vs tolerance.
  - [ ] Confirm — output present as a real alternative in the comparison.
- [ ] **P4-BE-6** — Deterministic pre-filter — drop hypotheses that violate budget / limits before LLM reasoning.
  - Test: `tests/agents/test_prefilter.py` — a hypothesis over max hedge ratio / notional / budget is removed with a logged reason before the manager sees it.
  - [ ] Confirm — force an over-budget hypothesis; it never reaches the manager prompt (check the log).
- [ ] **P4-BE-7** — Strategy Manager — validation stage.
  - Test: `tests/agents/test_manager_validate.py` — malformed hypothesis rejected; all-NOT_VIABLE input → `NO_TRADE`.
  - [ ] Confirm — feed 4 NOT_VIABLE hypotheses; decision is `NO_TRADE`.
- [ ] **P4-BE-8** — Strategy Manager — comparison stage (cost, protection, Greeks, tradeoffs via quant).
  - Test: `tests/agents/test_manager_compare.py` — comparison table has one row per viable hypothesis with the same metric keys; numbers sourced from `quant/`.
  - [ ] Confirm — comparison table renders with consistent columns.
- [ ] **P4-BE-9** — Strategy Manager — contextual reasoning + selection (`SELECT_STRATEGY` / `NO_TRADE` / `REASSESS`).
  - Test: `tests/agents/test_manager_select.py` (stubbed LLM) — given fixed inputs, selection is deterministic and cites the winning metric; low-confidence context → `REASSESS`.
  - [ ] Confirm — same input twice → same decision + rationale.
- [ ] **P4-BE-10** — Prompt templates for each agent and the manager.
  - Test: `tests/agents/test_prompts.py` — templates render with a sample context, no unfilled placeholders, within the token budget.
  - [ ] Confirm — dump a rendered prompt; it reads correctly and is complete.
- [ ] **P4-BE-11** — `POST /strategy/evaluate` — consumes `HedgeContext`, returns `StrategyDecision` + hypotheses.
  - Test: `tests/api/test_strategy_evaluate.py` — 200; body validates; persists 4 hypotheses + 1 decision.
  - [ ] Confirm — `curl -XPOST /strategy/evaluate` with a real context; decision + 4 hypotheses returned.
- [ ] **P4-BE-12** — Tests — each agent emits a valid hypothesis; manager selection is deterministic given fixed inputs. *(test task for P4-BE-2..9)*
  - Test: the suite above under `tests/agents/`.
  - [ ] Confirm — `pytest tests/agents -q` green.

### Frontend
- [x] **P4-FE-1** — `StrategyComparison` — hypotheses side by side (cost / protection / verdict).
  - Test: `src/components/StrategyComparison.test.tsx` (MSW) — one column per hypothesis; NOT_VIABLE styled distinctly; selected one highlighted.
  - [x] Confirm — real data: 4 columns, the selected strategy is visibly marked.
- [x] **P4-FE-2** — `Recommendation` panel — current risk, current vs target hedge, action, selected strategy.
  - Test: `src/components/Recommendation.test.tsx` — shows action verb (`SELECT` / `NO_TRADE` / `REASSESS`) and the hedge gap.
  - [x] Confirm — panel matches the `/strategy/decision` payload.
- [x] **P4-FE-3** — `StrategyDetails` page — payoff chart, Greeks, cost, protection, tradeoffs.
  - Test: `src/routes/StrategyDetails.test.tsx` — `/strategy/:id` loads that hypothesis; renders `PayoffChart` + `Greeks` from its data.
  - [x] Confirm — open a hypothesis; chart and Greeks match its legs.
- [x] **P4-FE-4** — Bind `PayoffChart` to real hypothesis payoff data.
  - Test: `PayoffChart.test.tsx::real-data` — curve from a real hypothesis matches `quant/payoff` output within tolerance.
  - [x] Confirm — protective-put curve shows the expected floor at the strike.
- [x] **P4-FE-5** — Show rejected-hypothesis reasoning (why NOT_VIABLE).
  - Test: `StrategyComparison.test.tsx::rejected` — hovering / expanding a NOT_VIABLE column reveals `rejection_reason`.
  - [x] Confirm — a rejected strategy shows its reason in the UI.

**Phase 4 acceptance**
- [ ] `POST /strategy/evaluate` returns a reasoned `StrategyDecision` + 4 hypotheses.
- [ ] All-NOT_VIABLE input → `NO_TRADE`; deterministic selection on fixed input.
- [x] Rejected hypotheses persisted with reasons and visible in the UI.
- [ ] `pytest tests/agents -q` green.

---

## Phase 5 — Risk gate & execution

The non-negotiable safety layer, then the first real paper trade.

### DB
- [ ] **P5-DB-1** — `risk_checks` repository — approvals, rejections, modifications, violations, warnings.
  - Test: `tests/db/test_risk_checks_repo.py` — one row per risk evaluation; `violations` non-empty on REJECT; `modifications` non-empty on MODIFY.
  - [ ] Confirm — after `/execute`, `select verdict, violations from risk_checks` reflects the decision.
- [ ] **P5-DB-2** — `orders` + `fills` repository.
  - Test: `tests/db/test_orders_repo.py` — order persists with legs; fills link to the order; status transitions monotonic.
  - [ ] Confirm — after a paper trade, `orders` + `fills` rows match Alpaca's order history.
- [ ] **P5-DB-3** — Persist `slippage` and `execution_failures`.
  - Test: `tests/db/test_orders_repo.py::test_slippage` — slippage = fill price − expected price; a failed submit writes an `execution_failures` row.
  - [ ] Confirm — `select leg_symbol, slippage from fills` populated after a fill.
- [ ] **P5-DB-4** — Read endpoints: `GET /risk/checks?cycle_id=`, `GET /orders?cycle_id=`.
  - Test: `tests/api/test_exec_readback.py` — both filter by `cycle_id`; orders include nested fills.
  - [ ] Confirm — `curl` both; data matches the DB.

### Backend
- [ ] **P5-BE-1** — Deterministic risk engine — hedge-budget check.
  - Test: `tests/agents/test_risk_budget.py` — cost > budget → fail with the numbers; cost = budget → pass.
  - [ ] Confirm — over-budget plan is blocked before any LLM call.
- [ ] **P5-BE-2** — Position limits + max hedge ratio + max notional checks.
  - Test: `tests/agents/test_risk_limits_engine.py` — each limit breached individually → distinct violation code; at-limit → pass.
  - [ ] Confirm — a plan over max hedge ratio is rejected with that specific reason.
- [ ] **P5-BE-3** — Buying-power + liquidity checks.
  - Test: `tests/agents/test_risk_bp_liquidity.py` — insufficient buying power → fail; wide bid/ask or low OI → liquidity warning/fail per threshold.
  - [ ] Confirm — a strike with no quotes is rejected as illiquid.
- [ ] **P5-BE-4** — Contract-validity + expiration checks.
  - Test: `tests/agents/test_risk_contract.py` — unknown/expired contract → fail; expiry inside the min window → fail.
  - [ ] Confirm — an already-expired option is rejected.
- [ ] **P5-BE-5** — Greeks-bounds + multi-leg consistency checks.
  - Test: `tests/agents/test_risk_greeks_multileg.py` — net delta outside band → fail; put-spread with inverted strikes → fail; collar missing a leg → fail.
  - [ ] Confirm — a malformed 2-leg plan is rejected for inconsistency.
- [ ] **P5-BE-6** — Execution-tolerance / price-band check.
  - Test: `tests/agents/test_risk_price_band.py` — limit price outside the allowed % of mid → fail.
  - [ ] Confirm — a plan priced 20% off mid is rejected.
- [ ] **P5-BE-7** — Risk-engine aggregator → structured pass/fail with per-check reasons.
  - Test: `tests/agents/test_risk_engine.py` — aggregate result lists every check with pass/fail + reason; any hard fail → overall REJECT.
  - [ ] Confirm — output shows the full checklist, not just a boolean.
- [ ] **P5-BE-8** — Risk Agent — `APPROVE` / `MODIFY` / `REJECT`; cannot override a deterministic fail, cannot invent a strategy.
  - Test: `tests/agents/test_risk_agent.py` (stubbed LLM) — LLM "approve" on a deterministically-failed plan is forced to REJECT; LLM cannot change `strategy_type`.
  - [ ] Confirm — inject a failing plan + an approving LLM stub; result is REJECT.
- [ ] **P5-BE-9** — `RiskDecision` output + `risk_checks` persistence.
  - Test: `tests/agents/test_risk_agent.py::test_persist` — decision validates as `RiskDecision`; a `risk_checks` row is written.
  - [ ] Confirm — `select * from risk_checks order by id desc limit 1` after a run.
- [ ] **P5-BE-10** — Execution Agent — build `ExecutionPlan` from an approved decision.
  - Test: `tests/agents/test_execution_plan.py` — plan legs match the approved hypothesis; MODIFY adjustments applied.
  - [ ] Confirm — approved decision → plan with the exact legs/quantities.
- [ ] **P5-BE-11** — Pre-flight validation before submit (re-check contract, price, buying power).
  - Test: `tests/agents/test_preflight.py` — stale quote or drifted price since approval → abort before submit, no order sent.
  - [ ] Confirm — mock a price move; submit is skipped with a logged reason.
- [ ] **P5-BE-12** — Multi-leg order submission via Alpaca MCP (combo order preferred over independent legs).
  - Test: `tests/integrations/test_alpaca_submit.py` — builds one multi-leg order payload; falls back to legged submit only when combo is unsupported.
  - [ ] Confirm — `pytest -m smoke` submits a 2-leg paper order; Alpaca shows one combo order.
- [ ] **P5-BE-13** — Legging-risk / partial-fill recovery path; never report false success.
  - Test: `tests/agents/test_partial_fill.py` — one leg fills, one doesn't → result is `PARTIALLY_FILLED`, unfilled leg flagged, recovery action recorded.
  - [ ] Confirm — simulate a partial fill; result is not `FILLED`.
- [ ] **P5-BE-14** — `ExecutionResult` mapping (`FILLED` / `PARTIALLY_FILLED` / `FAILED` / `CANCELLED`) + fills persistence.
  - Test: `tests/agents/test_execution_result.py` — each Alpaca terminal state maps to the right enum; fills written with prices.
  - [ ] Confirm — after a live paper fill, result is `FILLED` and `fills` rows exist.
- [ ] **P5-BE-15** — `POST /execute` endpoint — decision → plan → order → result.
  - Test: `tests/api/test_execute.py` — 200; body validates as `ExecutionResult`; persists risk check + order + fills.
  - [ ] Confirm — `curl -XPOST /execute` for an approved decision; a paper trade appears in Alpaca.
- [ ] **P5-BE-16** — Tests — deterministic reject blocks an LLM approve; a partial fill yields a truthful result. *(test task for P5-BE-8/13)*
  - Test: the two suites above.
  - [ ] Confirm — `pytest tests/agents/test_risk_agent.py tests/agents/test_partial_fill.py -q` green.

### Frontend
- [ ] **P5-FE-1** — `HedgeStatus` — current strategy, hedge cost, protection level, expiration, hedge P&L.
  - Test: `src/components/HedgeStatus.test.tsx` (MSW) — renders each field; no active hedge → "unhedged" state.
  - [ ] Confirm — after a paper trade, `HedgeStatus` matches the order.
- [ ] **P5-FE-2** — Risk-check checklist in `Recommendation` / `AgentActivity` (Budget ✓ / Liquidity ✓ / Exposure ✓ / Position size ✓).
  - Test: `src/components/RiskChecklist.test.tsx` — one line per check with pass/fail icon; failed check shows its reason.
  - [ ] Confirm — checklist mirrors the `/risk/checks` payload.
- [ ] **P5-FE-3** — Order-status indicator (submitted / partial / filled / failed).
  - Test: `src/components/OrderStatus.test.tsx` — each status renders a distinct badge; polling updates on change.
  - [ ] Confirm — watch the badge move submitted → filled during a paper trade.
- [ ] **P5-FE-4** — Surface MODIFY / REJECT reasons.
  - Test: `RiskChecklist.test.tsx::modify-reject` — MODIFY shows the adjustment, REJECT shows the blocking violation.
  - [ ] Confirm — force a REJECT; the reason is visible in the UI.

**Phase 5 acceptance**
- [ ] A deterministically-failing plan is REJECTed even with an approving LLM stub.
- [ ] First real multi-leg **paper** trade submitted; `orders` + `fills` + `risk_checks` all written.
- [ ] Partial fill → `PARTIALLY_FILLED` (never a false `FILLED`).
- [ ] `HedgeStatus` + risk checklist + order status render against real endpoints.

---

## Phase 6 — Orchestrator & autonomous loop

Wire Phases 3–5 into one stateful pass. First hands-off cycle.

### DB
- [ ] **P6-DB-1** — `workflow_state` table / columns — cycle_id, current_node, status, updated_at.
  - Test: `tests/db/test_schema.py::test_workflow_state` — columns + `current_node` constrained to the node enum.
  - [ ] Confirm — `\d workflow_state` matches.
- [ ] **P6-DB-2** — Persist node transitions so a restart resumes the decision history (Tech-Stack §21).
  - Test: `tests/e2e/test_resume.py` — kill the process mid-cycle, restart → run continues from the last persisted node, no duplicate orders.
  - [ ] Confirm — Ctrl-C during `ANALYZING`, restart; the cycle resumes, doesn't restart.
- [ ] **P6-DB-3** — `GET /cycle/:id/state` endpoint.
  - Test: `tests/api/test_cycle_state.py` — returns current node + status + transition history for the cycle.
  - [ ] Confirm — `curl /cycle/<id>/state` during a run shows the node advancing.

### Backend
- [ ] **P6-BE-1** — LangGraph state-machine skeleton — nodes `INITIAL → ANALYZING → STRATEGY_EVALUATION → RISK_CHECK → EXECUTION → MONITORING`.
  - Test: `tests/agents/test_graph_shape.py` — graph compiles; edges match the spec; no unreachable node.
  - [ ] Confirm — render the graph; the six nodes chain in order.
- [ ] **P6-BE-2** — Node: `ANALYZING` wraps the Phase 3 chain and builds `HedgeContext`.
  - Test: `tests/agents/test_node_analyzing.py` — node output state carries a valid `HedgeContext`; agent failure sets `degraded`.
  - [ ] Confirm — run the node alone; context is populated.
- [ ] **P6-BE-3** — Node: `STRATEGY_EVALUATION` wraps Phase 4.
  - Test: `tests/agents/test_node_strategy.py` — consumes state `HedgeContext`, writes `StrategyDecision`; `NO_TRADE` routes toward `MONITORING`.
  - [ ] Confirm — run the node; decision present in state.
- [ ] **P6-BE-4** — Node: `RISK_CHECK` wraps the Phase 5 risk gate.
  - Test: `tests/agents/test_node_risk.py` — REJECT routes to `MONITORING` (no execution); APPROVE/MODIFY routes to `EXECUTION`.
  - [ ] Confirm — a REJECT decision never reaches `EXECUTION`.
- [ ] **P6-BE-5** — Node: `EXECUTION` wraps Phase 5 execution.
  - Test: `tests/agents/test_node_execution.py` — writes `ExecutionResult` to state; `FAILED` recorded, not swallowed.
  - [ ] Confirm — run with an approved decision; result in state + DB.
- [ ] **P6-BE-6** — Node: `MONITORING` placeholder handing off to Phase 7.
  - Test: `tests/agents/test_node_monitoring_stub.py` — node is terminal for the cycle and persists `MonitoringState`.
  - [ ] Confirm — cycle ends in `MONITORING` with a state row.
- [ ] **P6-BE-7** — Agent routing + dependency management + result collection between nodes.
  - Test: `tests/agents/test_routing.py` — conditional edges (`NO_TRADE`, `REJECT`, `REASSESS`) go to the right next node.
  - [ ] Confirm — exercise all three branches; each lands correctly.
- [ ] **P6-BE-8** — Retry logic per node (bounded, backoff).
  - Test: `tests/agents/test_retry.py` — transient error retried up to N with backoff; exhausted → classified failure, not an infinite loop.
  - [ ] Confirm — inject 2 transient failures; node succeeds on retry 3.
- [ ] **P6-BE-9** — Failure classifier — critical (halt, do not trade) vs recoverable (degrade context, record the limitation) per BRD §31.
  - Test: `tests/agents/test_failure_classifier.py` — Alpaca auth error → critical (halt); one news source down → recoverable (degrade + note).
  - [ ] Confirm — pull Alpaca creds mid-run; the cycle halts before `EXECUTION`.
- [ ] **P6-BE-10** — State-persistence hook fired on every transition.
  - Test: `tests/agents/test_persist_hook.py` — every node entry/exit writes a `workflow_state` update with a timestamp.
  - [ ] Confirm — `select current_node, updated_at from workflow_state` shows each step.
- [ ] **P6-BE-11** — `POST /run-cycle` trigger.
  - Test: `tests/api/test_run_cycle.py` — 202/200; returns a `cycle_id`; a full cycle completes against stubbed externals.
  - [ ] Confirm — `curl -XPOST /run-cycle`; the cycle runs end to end on the paper account.
- [ ] **P6-BE-12** — `GET /workflow-state` + SSE stream of the current node.
  - Test: `tests/api/test_workflow_stream.py` — SSE emits a message per transition; closes when the cycle ends.
  - [ ] Confirm — `curl -N /workflow-state`; events stream as the cycle advances.
- [ ] **P6-BE-13** — End-to-end test — one hands-off cycle on the paper account.
  - Test: `tests/e2e/test_full_cycle.py` `@pytest.mark.smoke` — `/run-cycle` → all nodes visited → either a paper trade or a justified `NO_TRADE`, fully persisted.
  - [ ] Confirm — one `/run-cycle` with no human input produces a complete, auditable trail.

### Frontend
- [ ] **P6-FE-1** — Live workflow-state indicator (current node, progress).
  - Test: `src/components/WorkflowState.test.tsx` (MSW SSE mock) — highlights the active node; shows done/failed terminal states.
  - [ ] Confirm — run a cycle; the indicator tracks the backend node.
- [ ] **P6-FE-2** — `AgentActivity` streaming the full chain end to end (SSE / websocket / poll).
  - Test: `AgentActivity.test.tsx::streaming` — appends events as they arrive; ordering preserved; reconnects after a drop.
  - [ ] Confirm — timeline fills live during `/run-cycle`.
- [ ] **P6-FE-3** — "Run cycle" demo control with disabled / in-progress states.
  - Test: `src/components/RunCycleButton.test.tsx` — disabled while a cycle runs; re-enabled on completion/failure.
  - [ ] Confirm — click once; button locks until the cycle ends.
- [ ] **P6-FE-4** — Error banner when a cycle halts on a critical failure.
  - Test: `WorkflowState.test.tsx::critical` — critical-failure event → banner with the reason; no trade shown.
  - [ ] Confirm — trigger a critical failure; the banner explains the halt.

**Phase 6 acceptance**
- [ ] One `POST /run-cycle` completes hands-off: all nodes visited, trail persisted.
- [ ] REJECT / `NO_TRADE` branches never execute a trade.
- [ ] Kill-and-restart mid-cycle resumes from the last node (no duplicate orders).
- [ ] `tests/e2e/test_full_cycle.py` green; frontend tracks the loop live.

---

## Phase 7 — Monitoring & adaptive rebalancing

Close the loop. This is the differentiator — the system increases, decreases,
replaces, or removes protection rather than just accumulating puts.

### DB
- [ ] **P7-DB-1** — `monitoring_events` repository (trigger type, observed values, threshold, fired_at).
  - Test: `tests/db/test_monitoring_repo.py` — a Level-1 check that crosses its threshold writes exactly one event; below threshold writes none.
  - [ ] Confirm — `select trigger_type, threshold from monitoring_events` after a monitored cycle.
- [ ] **P7-DB-2** — `reassessment_events` repository (trigger → outcome).
  - Test: `tests/db/test_monitoring_repo.py::test_reassessment` — each Level-2 run links its triggering event and stores the outcome enum.
  - [ ] Confirm — `select outcome from reassessment_events` shows `MAINTAIN`/`DECREASE`/etc.
- [ ] **P7-DB-3** — `hedge_changes` repository (before / after hedge, delta, reason).
  - Test: `tests/db/test_monitoring_repo.py::test_hedge_changes` — an adjustment writes before/after ratio + signed delta + reason.
  - [ ] Confirm — after a DECREASE, `select * from hedge_changes` shows the reduction.
- [ ] **P7-DB-4** — Persist `MonitoringState` (`current_hedge`, `target_hedge`, `cooldown_until`, `trigger_history[]`, `monitoring_status`).
  - Test: `tests/db/test_monitoring_repo.py::test_state` — round-trips; `trigger_history` append-only; `cooldown_until` nullable.
  - [ ] Confirm — `GET /monitoring/state` matches the row.
- [ ] **P7-DB-5** — Endpoints: `GET /monitoring/state`, `GET /monitoring/events`.
  - Test: `tests/api/test_monitoring_readback.py` — state returns current vs target; events filter by `cycle_id` and order by `fired_at`.
  - [ ] Confirm — `curl` both; data matches the DB.

### Backend
- [ ] **P7-BE-1** — Monitoring Agent — Level 1 deterministic checks: drawdown, hedge drift, volatility, exposure, expiration, major state change. Does not trade.
  - Test: `tests/agents/test_monitor_level1.py` — each check fires only past its threshold; the agent has no execution path (asserted — no order calls).
  - [ ] Confirm — feed a drifted portfolio; a `hedge_drift` event fires, no order is placed.
- [ ] **P7-BE-2** — Trigger evaluators: hedge drift, drawdown change, volatility change, event, expiration, emergency.
  - Test: `tests/agents/test_triggers.py` — one focused case per trigger type → correct type + payload.
  - [ ] Confirm — synthesize each condition; the matching trigger type is emitted.
- [ ] **P7-BE-3** — Deadband filter — ignore sub-threshold deviations.
  - Test: `tests/agents/test_deadband.py` — a deviation inside the band produces no event; just outside produces one.
  - [ ] Confirm — nudge hedge ratio by < deadband; nothing fires.
- [ ] **P7-BE-4** — Cooldown after an adjustment, with emergency-trigger bypass.
  - Test: `tests/agents/test_cooldown.py` — a normal trigger during cooldown is suppressed; an emergency trigger bypasses it.
  - [ ] Confirm — adjust, then immediately trip a normal trigger (suppressed) and an emergency trigger (passes).
- [ ] **P7-BE-5** — Level 2 intelligent reassessment — routes back into the orchestrator with context.
  - Test: `tests/agents/test_level2_route.py` — a fired trigger re-enters the graph at `STRATEGY_EVALUATION` with the trigger + current hedge in context.
  - [ ] Confirm — a trigger starts a new reassessment cycle carrying the trigger reason.
- [ ] **P7-BE-6** — Reassessment outcomes: `MAINTAIN` / `INCREASE` / `DECREASE` / `REMOVE` / `REPLACE` / `NO_TRADE`.
  - Test: `tests/agents/test_reassessment_outcomes.py` (stubbed LLM) — each context shape yields the expected outcome enum; outcome is schema-bound.
  - [ ] Confirm — a stabilization context yields `DECREASE` or `REMOVE`.
- [ ] **P7-BE-7** — Apply-change path — `DECREASE` / `REMOVE` / `REPLACE` produce a new `ExecutionPlan` through the risk gate.
  - Test: `tests/agents/test_apply_change.py` — `DECREASE` → a sell/close plan that still passes the risk gate; `REMOVE` → full close; `REPLACE` → close + open.
  - [ ] Confirm — a `DECREASE` outcome results in a real paper order that reduces the hedge.
- [ ] **P7-BE-8** — `MONITORING` node runs Level 1 each cycle and escalates to Level 2 on a trigger.
  - Test: `tests/agents/test_node_monitoring.py` — no trigger → cycle ends; trigger → Level 2 dispatched once (not looping).
  - [ ] Confirm — run two cycles: quiet one ends clean, triggered one escalates.
- [ ] **P7-BE-9** — `POST /monitor` (manual tick) + a scheduled tick for the demo.
  - Test: `tests/api/test_monitor.py` — manual tick returns fired triggers (or none); scheduler registers the job.
  - [ ] Confirm — `curl -XPOST /monitor`; response lists current triggers.
- [ ] **P7-BE-10** — Test — stabilization scenario reduces the hedge; an emergency bypasses cooldown. *(test task for P7-BE-4/6/7)*
  - Test: `tests/e2e/test_adaptation.py` — scripted "vol spike → hedge on → vol falls → hedge reduced"; separately, an emergency trigger fires inside cooldown.
  - [ ] Confirm — the end-to-end stabilization script reduces the hedge without human input.

### Frontend
- [ ] **P7-FE-1** — Monitoring / triggers panel — active triggers + history.
  - Test: `src/components/MonitoringPanel.test.tsx` (MSW) — lists active triggers; history ordered by `fired_at`; empty → "all clear".
  - [ ] Confirm — panel matches `/monitoring/events`.
- [ ] **P7-FE-2** — Current-vs-target hedge-drift gauge.
  - Test: `src/components/HedgeDriftGauge.test.tsx` — needle at current, marker at target; inside deadband styled calm, outside styled alert.
  - [ ] Confirm — gauge matches `current_hedge` vs `target_hedge` from state.
- [ ] **P7-FE-3** — Reassessment history list (trigger → outcome → hedge change).
  - Test: `src/components/ReassessmentHistory.test.tsx` — one row per reassessment linking trigger, outcome, and the resulting `hedge_changes` delta.
  - [ ] Confirm — a `DECREASE` shows trigger, outcome, and the ratio drop.
- [ ] **P7-FE-4** — "Market stabilizes → reduce hedge" narrative view (BRD §37 Scene 8).
  - Test: `src/routes/AdaptationStory.test.tsx` — renders the timeline of hedge-on → hedge-reduced with the triggering events.
  - [ ] Confirm — the demo view tells the reduction story from real data.

**Phase 7 acceptance**
- [ ] Level 1 never trades; only Level 2 (via the risk gate) does.
- [ ] Deadband suppresses noise; cooldown holds except for emergencies.
- [ ] Scripted stabilization run reduces/removes the hedge hands-off (`tests/e2e/test_adaptation.py`).
- [ ] Monitoring panel + drift gauge + reassessment history render against real endpoints.

---

## Phase 8 — Dashboard, P&L & demo hardening

Assemble the full experience and make the agent's behavior visible.

### DB
- [ ] **P8-DB-1** — Populate `performance` — portfolio P&L, hedge P&L, net P&L, drawdown, hedge cost per cycle.
  - Test: `tests/db/test_performance_repo.py` — one row per cycle; `net_pnl = portfolio_pnl + hedge_pnl`; drawdown from `quant/`.
  - [ ] Confirm — `select * from performance order by ts` after several cycles; the identity holds.
- [ ] **P8-DB-2** — Store the unhedged-benchmark series.
  - Test: `tests/db/test_performance_repo.py::test_benchmark` — benchmark row per timestamp; equals portfolio value with hedge legs excluded.
  - [ ] Confirm — benchmark diverges from net only after a hedge is placed.
- [ ] **P8-DB-3** — Add indexes / materialized queries tuned for dashboard reads.
  - Test: `tests/db/test_performance_repo.py::test_dashboard_query_plan` — the dashboard aggregate query uses an index (`EXPLAIN` assertion); p95 under a set budget on the seed dataset.
  - [ ] Confirm — dashboard endpoints respond < 200 ms on the demo dataset.
- [ ] **P8-DB-4** — Export and back up the demo dataset.
  - Test: CI job `demo-restore` — `pg_dump` then restore into a fresh DB; row counts match.
  - [ ] Confirm — restore the dump locally; dashboard renders identically.

### Backend
- [ ] **P8-BE-1** — P&L endpoints — time series + current snapshot.
  - Test: `tests/api/test_pnl.py` — series endpoint returns ordered points; snapshot matches the latest `performance` row.
  - [ ] Confirm — `curl /pnl/series` and `/pnl/current`; numbers reconcile with the DB.
- [ ] **P8-BE-2** — Unhedged-benchmark computation (hedged vs unhedged, BRD §36).
  - Test: `tests/api/test_pnl.py::test_vs_benchmark` — before any hedge, hedged == unhedged; after a protective put in a drop, hedged drawdown < unhedged.
  - [ ] Confirm — comparison endpoint shows the hedge cushioning a simulated drawdown.
- [ ] **P8-BE-3** — Observability polish — structured log line per: agent invocation, input summary, output, decision, tool call, risk check, order, fill, error, reassessment trigger.
  - Test: `tests/agents/test_observability.py` — a full cycle emits at least one structured record of each type with a shared `cycle_id`.
  - [ ] Confirm — grep the logs for one `cycle_id`; every event type is present.
- [ ] **P8-BE-4** — Decision-trail endpoint — one trade → risk approval → strategy decision → hypotheses → analysis context → trigger.
  - Test: `tests/api/test_decision_trail.py` — given an `order_id`, returns the full linked chain; a missing link is reported, not silently dropped.
  - [ ] Confirm — `curl /decision-trail/<order_id>`; every hop is present and linked.
- [ ] **P8-BE-5** — Deployment config — env templating, CORS, health checks, start commands.
  - Test: CI `deploy-dryrun` — container builds; `/health` green; CORS allows the frontend origin only.
  - [ ] Confirm — deploy to staging; `/health` green, frontend can call it.
- [ ] **P8-BE-6** — Seed / replay script that reproduces the full demo narrative.
  - Test: `tests/e2e/test_demo_replay.py` — the script runs the scripted scenes and asserts the expected trades + reassessments land.
  - [ ] Confirm — `python -m backend.demo_replay` produces the exact demo state.

### Frontend
- [ ] **P8-FE-1** — `Performance` component — hedged vs unhedged chart + P&L tiles.
  - Test: `src/components/Performance.test.tsx` (MSW) — two series drawn; tiles show net / portfolio / hedge P&L; negative values styled.
  - [ ] Confirm — chart matches `/pnl/series` + benchmark.
- [ ] **P8-FE-2** — Full dashboard assembly — Portfolio / Risk / Hedge / Recommendation / StrategyComparison / AgentActivity / TradeHistory / Performance.
  - Test: `src/routes/Dashboard.test.tsx` — every panel mounts with its endpoint mocked; one failing panel doesn't blank the page.
  - [ ] Confirm — load `/` against the live backend; all panels populate.
- [ ] **P8-FE-3** — Decision-trail drill-down UI.
  - Test: `src/components/DecisionTrail.test.tsx` — clicking a trade expands trade → risk → strategy → hypotheses → context → trigger.
  - [ ] Confirm — drill from a real trade to its originating trigger.
- [ ] **P8-FE-4** — `Configuration` page — RiskPreferences / HedgePreferences / AutonomySettings, persisted.
  - Test: `src/routes/Configuration.test.tsx` — edits validate, save `PATCH`es, reload shows the saved values; invalid input blocked.
  - [ ] Confirm — change a risk preference, reload, it sticks and affects the next cycle.
- [ ] **P8-FE-5** — `TradeHistory` component.
  - Test: `src/components/TradeHistory.test.tsx` — one row per order with status + fills; sortable by date; empty state.
  - [ ] Confirm — history matches `/orders`.
- [ ] **P8-FE-6** — Demo-script polish — deterministic walkthrough + reset button.
  - Test: `src/routes/Dashboard.test.tsx::reset` — reset returns the UI to the seed state without a page reload.
  - [ ] Confirm — run the demo, hit reset, re-run; identical result.
- [ ] **P8-FE-7** — Deploy — Vercel (frontend) + Railway / Render (backend) + Neon (DB) + Alpaca paper trading.
  - Test: post-deploy smoke `tests/e2e/test_prod_smoke.py` — hosted `/health` green; one `/run-cycle` on the hosted stack completes.
  - [ ] Confirm — open the deployed URL; run a full cycle end to end in the browser.

**Phase 8 acceptance**
- [ ] Dashboard renders every panel from live endpoints; one panel failing degrades gracefully.
- [ ] Hedged-vs-unhedged comparison shows the hedge reducing drawdown.
- [ ] Decision-trail drills from any trade back to its trigger.
- [ ] Deployed stack runs one hands-off cycle from the public URL.
- [ ] `python -m backend.demo_replay` reproduces the demo deterministically.

---

## Sequencing notes

- **Phases 1–2 can overlap:** frontend scaffold + DB migrations run alongside the
  quant engine.
- **Phase 3 onward is mostly serial** on the backend — each layer consumes the
  previous layer's contract.
- **Frontend can trail by one phase** working against stubbed endpoints, then
  swap to real ones when a backend phase lands.
- **Do not start Phase 6** until Phases 3–5 each pass their own done-criteria in
  isolation; debugging the loop is far harder than debugging a stage.
- **Write the Test before the implementation** (RED → GREEN). A task is not done
  until its Test is GREEN and its **Confirm** box is `[x]`.
