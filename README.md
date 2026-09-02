# Autonomous Adaptive Portfolio Hedge Agent

Backend + DB + ops for an agent that turns a live Alpaca **paper** portfolio into
a standardized `HedgeContext`, reasons over competing hedge strategies, runs
every candidate through a deterministic risk gate, executes multi-leg option
hedges, and then keeps adjusting protection as the market moves.

- Architecture and rationale: `docs/Autonomous_Adaptive_Portfolio_Hedge_Agent_BRD_v1.0.md`
- Tech stack: `docs/Autonomous_Adaptive_Portfolio_Hedge_Agent_Tech_Stack.md`
- Task-by-task plan (the source of truth for scope): `docs/phased-implementation-plan.md`

---

## Run it yourself

### Prerequisites

- **Python 3.11+**
- A **PostgreSQL** connection string — a free [Neon](https://neon.tech) project
  works. You need the *pooled* DSN (app runtime) and, ideally, the *direct /
  unpooled* DSN (migrations).
- **Node 20+** — only for the frontend (`frontend/`, owned by Antigravity; may
  not be scaffolded yet).
- `make` — optional, every target has a spelled-out fallback below.

### 1. Install and sanity-check the backend

This block is what CI's `docs-commands` job runs on every PR, so it stays honest:

```bash ci
python -m pip install --upgrade pip
pip install -r requirements.txt
python -c "import backend.api, backend.agents, backend.quant, backend.integrations, backend.state, backend.models, backend.services, backend.config; print('backend imports OK')"
pytest -q -m "not smoke" tests/api/test_health.py tests/ops/test_makefile.py tests/config/test_env_example.py
```

### 2. Configure the environment

```bash
cp .env.example .env
# edit .env — at minimum set DATABASE_URL (and DATABASE_URL_UNPOOLED for migrations)
python scripts/check_env.py            # lists any required keys still missing; exits non-zero if so
```

### 3. Create the schema and load the demo portfolio

```bash
make migrate && make seed
# no make:
python -m alembic -c backend/alembic.ini upgrade head
python -m backend.seed
```

### 4. Boot the API and hit it

```bash
make dev
# no make:
python -m uvicorn backend.api.app:app --reload --host 0.0.0.0 --port 8000
```

```bash
curl -s localhost:8000/health        # -> {"status":"ok","version":"...","build":{...}}
```

### 5. Run the tests

```bash
make test                            # or: pytest -q
make smoke                           # live Alpaca / LLM calls — needs real keys
make cov                             # coverage report
```

### 6. Frontend (when scaffolded)

```bash
cd frontend
npm install
npm run dev                          # Vite dev server, talks to the API on :8000
npm test                             # vitest + React Testing Library + MSW
npm run build && npx tsc --noEmit
```

---

## How to read a task's `Test:` / `Confirm:` lines

Every task in `docs/phased-implementation-plan.md` carries two extra lines, and
both must be satisfied before the task is done:

- **`Test:`** — the *automated* proof. It names a test file / selection (paths
  are relative to `backend/` or `frontend/`). Write it first so it fails (RED),
  implement until it passes (GREEN). If a task says
  `Test: tests/api/test_health.py::test_health_ok`, then
  `pytest -q tests/api/test_health.py::test_health_ok` going green *is* the
  automated sign-off.
- **`Confirm:`** — a `- [ ]` checkbox with the *manual* gesture you run yourself
  (a `curl`, a `psql`/schema query, a screen to eyeball). Tick it only after you
  have personally seen it work, then check the task's own `- [ ]` box.

A **phase** is done when every `Confirm` in it is checked *and* that phase's
acceptance block passes:

```bash
make verify-phase-1                   # runs Phase 1's pytest selection + frontend subset,
                                      # then prints the "Phase 1 acceptance" checklist
```

`make verify-phase-1` … `verify-phase-8` exit non-zero (naming the failing test)
if anything in that phase's selection breaks.

---

## Make targets

| Target | Does |
|---|---|
| `make dev` | Boot the API with autoreload on `:8000` |
| `make test` / `make smoke` / `make cov` | Backend suite / smoke-only / coverage |
| `make migrate` / `make migrate-down` | Alembic up to head / down to base |
| `make seed` | Load the canonical demo portfolio |
| `make db-reset` / `make db-fresh` | Downgrade → migrate → reseed |
| `make demo-restore` | Restore the canonical demo dataset |
| `make openapi` | Regenerate the checked-in `openapi.json` |
| `make verify-phase-N` | Phase `N` tests + acceptance checklist (`N` = 1..8) |
| `make verify-all` | Every phase in order |

Run `make help` for the list from the Makefile itself.
