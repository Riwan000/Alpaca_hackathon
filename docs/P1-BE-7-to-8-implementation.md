# P1-BE-7 → P1-BE-8 — implementation notes

GitHub issues #23–#24. Phase 1 (Foundation & contracts), track: backend.
Source of truth: `docs/phased-implementation-plan.md`.

## Summary

| Issue | Task | Status |
|---|---|---|
| #23 | P1-BE-7 — Alpaca client wrapper (`integrations/alpaca/`) | done |
| #24 | P1-BE-8 — Alpaca connectivity smoke test | done (live paper account) |

Baseline before this work: 46 passed / 1 deselected (after #18–#22). This work
adds 8 non-smoke tests (`test_alpaca_client.py`) and 1 smoke test
(`test_alpaca_smoke.py`).

- `pytest -q` → **54 passed, 2 deselected**
- `pytest -q tests/integrations tests/llm` → **13 passed, 2 deselected**
- `pytest -m smoke tests/integrations` → **1 passed** — prints the paper account
  number (`PA3C0P4T6AJE`, status `ACTIVE`, 0 open positions).

---

## #23 — P1-BE-7: Alpaca client wrapper

- **`backend/integrations/alpaca/client.py`** (new) — a thin *synchronous*
  wrapper over the Alpaca trading REST API, HTTP layer is plain `httpx` so tests
  inject an `httpx.MockTransport`.
  - `AlpacaConfig(api_key, secret_key, base_url, paper)` — frozen dataclass, no
    client.
  - `resolve_alpaca_config(settings)` — reads `ALPACA_API_KEY` /
    `ALPACA_SECRET_KEY` (both `SecretStr`), `.get_secret_value().strip()` only at
    this boundary. Blank / whitespace-only key **or** secret → raise
    `AlpacaCredentialsError` (fail fast, no 403). `base_url` defaults to
    `https://paper-api.alpaca.markets` (the module constant `PAPER_BASE_URL`)
    when `ALPACA_BASE_URL` is unset.
  - `build_auth_headers(config)` — `{APCA-API-KEY-ID, APCA-API-SECRET-KEY}`,
    Alpaca's documented header names.
  - `AlpacaClient(settings=None, *, config=None, transport=None, timeout=10.0)` —
    builds one `httpx.Client` with the paper base URL + both auth headers.
    `transport` is only forwarded to `httpx.Client` when not `None`.
    Context-manager (`__enter__` / `__exit__` → `close()`).
    - `.base_url` / `.paper` — read-only views.
    - `.get_account() -> dict` — `GET /v2/account`.
    - `.get_positions() -> list[dict]` — `GET /v2/positions`; `None` → `[]`; a
      non-array body → `AlpacaError`.
    - `_get()` maps a non-2xx to `AlpacaError` (status + body text; **no**
      headers, so credentials never land in the message), any transport /
      timeout error (`httpx.HTTPError`) to `AlpacaError`, and a 2xx body that
      is not JSON (edge/proxy HTML) to `AlpacaError`.
- **`backend/integrations/alpaca/__init__.py`** — re-exports the public names.
- **`tests/integrations/__init__.py`** (new) — package marker.
- **`tests/integrations/test_alpaca_client.py`** (new, no network) —
  `build_auth_headers` uses Alpaca's header names; the client targets the paper
  base URL and sends both auth headers on the wire (asserted via a recording
  `MockTransport`); `get_account` returns parsed JSON; `get_positions` returns a
  list incl. the empty case; a 403 → `AlpacaError`; a `200` non-JSON body →
  `AlpacaError`; a `200` object body where an array is expected → `AlpacaError`
  (not a silent key list); a blank key → `AlpacaCredentialsError` before any
  request.

Confirm: instantiate `AlpacaClient(get_settings())` against the paper creds in
`.env` — no exception (exercised by the P1-BE-8 smoke test).

## #24 — P1-BE-8: Alpaca connectivity smoke test

- **`tests/integrations/test_alpaca_smoke.py`** (new) —
  `pytestmark = pytest.mark.smoke`. Self-skips when `resolve_alpaca_config`
  raises `AlpacaCredentialsError`. Otherwise: `get_account()` returns an object
  with a non-empty `id`, `get_positions()` returns a `list`, and the paper
  account number + status + open-position count are printed via
  `capsys.disabled()` (visible without `-s`).
- Deselected by default via `addopts = -m 'not smoke'`; run with
  `pytest -m smoke tests/integrations`.

Confirm (live): `pytest -m smoke tests/integrations` →
`Alpaca paper account: PA3C0P4T6AJE (status=ACTIVE, open positions=0)` — 1 passed.

---

## Running

```bash
pip install -r requirements.txt          # or:  pip install -e ".[dev]"
pytest                                    # full suite, smoke deselected
pytest -m smoke tests/integrations        # Alpaca connectivity (needs paper keys)
```

## New / changed files

```
backend/integrations/alpaca/__init__.py       (was empty — now re-exports)
backend/integrations/alpaca/client.py         (new — httpx wrapper)
tests/integrations/__init__.py                 (new)
tests/integrations/test_alpaca_client.py       (new — mocked transport)
tests/integrations/test_alpaca_smoke.py        (new — @pytest.mark.smoke)
```
