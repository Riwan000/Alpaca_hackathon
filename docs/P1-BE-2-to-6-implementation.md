# P1-BE-2 → P1-BE-6 — implementation notes

GitHub issues #18–#22. Phase 1 (Foundation & contracts), track: backend.
Source of truth: `docs/phased-implementation-plan.md`.

## Summary

| Issue | Task | Status |
|---|---|---|
| #18 | P1-BE-2 — dependency manifest | done |
| #19 | P1-BE-3 — FastAPI app factory + `GET /health` | done |
| #20 | P1-BE-4 — typed config loader, fail-fast, secret-safe | done |
| #21 | P1-BE-5 — `LLM_PROVIDER` abstraction (openrouter ↔ featherless) | done |
| #22 | P1-BE-6 — LLM smoke test | done (self-skips without live keys) |

Full suite: **46 passed, 1 deselected** (`smoke`). Baseline before this work was 21 passed.
(Verified by a fresh-context `verifier` pass — CONFIRMED; the `/debug/llm` degrade
and whitespace-key handling below were added in response to its caveats.)

---

## #18 — P1-BE-2: dependency manifest

- **`pyproject.toml`** (new) — `[project]` with the full runtime dependency set
  (fastapi, uvicorn, pydantic v2, pydantic-settings, httpx, alpaca-py, langgraph,
  openai, asyncpg, alembic, SQLAlchemy, psycopg). `[project.optional-dependencies].dev`
  = pytest, pytest-cov, pytest-asyncio. `[tool.pytest.ini_options]` registers the
  `smoke` / `unit` / `integration` markers and defaults to `-m 'not smoke'`.
  `[tool.coverage.run]` scopes coverage to `backend`.
- **`requirements.txt`** — rewritten from the DB-only stub to mirror
  `[project.dependencies]` + dev tools.
- **`tests/test_env.py`** (new) — `test_core_imports` asserts fastapi, pydantic (v2),
  alpaca, langgraph, httpx, uvicorn, asyncpg import at their pinned major versions
  (versions read via `importlib.metadata`, not module `__version__` — langgraph has none).

Confirm: `pip install -r requirements.txt` resolves with no conflicts; `pytest`
collects 44 tests with no import errors.

## #19 — P1-BE-3: FastAPI app factory + `GET /health`

- **`backend/__init__.py`** — adds `__version__ = "0.1.0"`.
- **`backend/api/app.py`** (new) — `create_app() -> FastAPI` factory: CORS from
  settings (falls back to localhost defaults if the env is incomplete), includes the
  health + debug routers. Module-level `app = create_app()` for
  `uvicorn backend.api.app:app`.
- **`backend/api/health.py`** (new) — `GET /health` → `200`
  `{"status": "ok", "version": <__version__>, "build": {"sha", "time", "environment"}}`.
  `sha` / `time` come from `BUILD_SHA` / `BUILD_TIME` env (CI-injected), default `"dev"`.
- **`backend/api/__init__.py`** — exports `app`, `create_app`.
- **`tests/api/test_health.py`** (new) — `test_health_ok` (200 + `version`),
  `test_health_reports_build_sha_from_env`.

Confirm (live): `uvicorn backend.api.app:app` →
`GET /health` = `{"status":"ok","version":"0.1.0","build":{"sha":"dev","time":"dev","environment":"development"}}`.

## #20 — P1-BE-4: typed config loader

- **`backend/config/settings.py`** — extends the existing `Settings` (P1-DB-1) with
  the full typed surface: LLM provider block, Alpaca block, external-data keys,
  server (`host`/`port`/`environment`/`log_level`/`cors_origins`), risk parameters.
  - `database_url` stays the only strictly-required key — the app can boot degraded
    without provider keys; each consumer checks its own key at its boundary.
  - All secrets are `SecretStr` / `SecretStr | None` → never in `repr`/`str`/logs.
  - `cors_origins` stored as a string; `cors_origins_list` property splits it
    (pydantic-settings would try to JSON-parse a `list` field from env and fail on
    the plain comma value).
  - New: `get_settings_or_exit(factory=get_settings)` — catches `ValidationError`,
    prints `configuration error: missing or invalid required setting(s): DATABASE_URL`
    to stderr, `raise SystemExit(1)`. Use at entrypoints.
- **`backend/config/__init__.py`** — also exports `get_settings_or_exit`, `LlmProvider`.
- **`tests/config/test_settings.py`** — adds: missing key raises + is named;
  `get_settings_or_exit` → `SystemExit(1)` + names the key; no secret value
  (LLM/Alpaca included) in `repr`/`str`; `llm_provider` toggle resolves
  base URL/model/key; `cors_origins` parses to a list. Existing P1-DB-1 tests unchanged.

Confirm (live): unset `DATABASE_URL` → process exits 1 with
`configuration error: missing or invalid required setting(s): DATABASE_URL`.

## #21 — P1-BE-5: `LLM_PROVIDER` abstraction

- **`backend/llm/provider.py`** (new) — one OpenAI-compatible client, two backends
  selected by `LLM_PROVIDER`:
  - `MODEL_MAP: {alias: {provider: model_id}}` for `fast` / `reasoning`; the
    `default` alias defers to the per-provider model from env (override without code).
  - `ProviderConfig(name, base_url, model, api_key)` — frozen dataclass, no client.
  - `resolve_model(alias, settings)` / `resolve_provider(settings, *, alias)`.
    An empty **or whitespace-only** env key (`OPENROUTER_API_KEY=`) resolves to
    `api_key=None` ("not configured"), not `""` — so consumers skip live calls
    instead of 401-ing.
  - `get_llm_client(settings, *, alias) -> openai.OpenAI` — client pointed at the
    resolved base URL (placeholder key if none, so construction never raises).
- **`backend/llm/__init__.py`** (new) — package exports.
- **`backend/api/debug.py`** (new) — `GET /debug/llm` echoes
  `{provider, model, base_url, api_key_configured}` (never the key itself); wired
  into `create_app()`. Degrades like `/health`: if settings fail to load
  (e.g. no `DATABASE_URL`), it falls back to a validation-free `Settings` and
  still returns 200 with the default LLM view.
- **`tests/llm/test_provider.py`** (new) — `test_toggle` (parametrized over both
  providers: right base URL + model + key, and the client's `base_url`),
  `test_model_alias_map`, secret-repr guard. No network.

Confirm (live): `LLM_PROVIDER=featherless` → `GET /debug/llm` =
`{"provider":"featherless","model":"meta-llama/Meta-Llama-3.1-70B-Instruct","base_url":"https://api.featherless.ai/v1","api_key_configured":false}`;
default (`openrouter`) resolves the openrouter base URL + model.

## #22 — P1-BE-6: LLM smoke test

- **`tests/llm/test_smoke.py`** (new) — `pytestmark = pytest.mark.smoke`. One real
  `chat.completions.create` (`max_tokens=8`, `temperature=0`) against the configured
  provider; asserts non-empty text. Self-skips when the active provider has no API key.
- Deselected by default via `addopts = -m 'not smoke'`; run explicitly with
  `pytest -m smoke tests/llm`.

Confirm: `pytest -m smoke tests/llm` — currently **skips** (no live key in `.env`).
With a real `OPENROUTER_API_KEY` / `FEATHERLESS_API_KEY` it runs one completion and
passes.

---

## Running

```bash
pip install -r requirements.txt          # or:  pip install -e ".[dev]"
pytest                                   # full suite, smoke deselected
pytest -m smoke tests/llm                # smoke (needs real LLM keys)
uvicorn backend.api.app:app --reload     # GET /health, GET /debug/llm
```

## New / changed files

```
pyproject.toml                     (new)
requirements.txt                   (rewritten)
backend/__init__.py                (+ __version__)
backend/config/__init__.py         (+ exports)
backend/config/settings.py         (full typed loader + get_settings_or_exit)
backend/api/__init__.py            (+ exports)
backend/api/app.py                 (new — create_app factory)
backend/api/health.py              (new — GET /health)
backend/api/debug.py               (new — GET /debug/llm)
backend/llm/__init__.py            (new)
backend/llm/provider.py            (new — provider abstraction + model map)
tests/test_env.py                  (new)
tests/config/test_settings.py      (+ P1-BE-4 tests)
tests/api/__init__.py              (new)
tests/api/test_health.py           (new)
tests/api/test_debug.py            (new)
tests/llm/__init__.py              (new)
tests/llm/test_provider.py         (new)
tests/llm/test_smoke.py            (new)
```
