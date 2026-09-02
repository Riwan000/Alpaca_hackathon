# P1-BE-9 → P1-BE-14 — implementation notes

GitHub issues #25–#30. Phase 1 (Foundation & contracts), track: backend.
Source of truth: `docs/phased-implementation-plan.md`, shapes from
`Autonomous_Adaptive_Portfolio_Hedge_Agent_BRD_v1.0.md` §14–§30.

## Summary

| Issue | Task | Module | Status |
|---|---|---|---|
| #25 | P1-BE-9  — `HedgeContext` contract | `backend/models/hedge_context.py` | done |
| #26 | P1-BE-10 — `StrategyHypothesis` / `StrategyDecision` | `backend/models/strategy.py` | done |
| #27 | P1-BE-11 — `RiskDecision` contract | `backend/models/risk.py` | done |
| #28 | P1-BE-12 — `ExecutionPlan` / `ExecutionResult` | `backend/models/execution.py` | done |
| #29 | P1-BE-13 — `MonitoringState` contract | `backend/models/monitoring.py` | done |
| #30 | P1-BE-14 — shared enums | `backend/models/enums.py` | done |

Baseline before this work: 54 passed / 2 deselected (after #18–#24). This work
adds 18 tests (`tests/models/test_contracts.py` ×5, `tests/models/test_enums.py`
×13 parametrized).

- `pytest -q` → **72 passed, 2 deselected**
- `pytest -q tests/models` → **18 passed**

## Design

- **`Contract` base** (`backend/models/common.py`) — every contract subclasses a
  pydantic v2 `BaseModel` with `model_config = ConfigDict(extra="forbid",
  frozen=True)`:
  - `extra="forbid"` — a fixture with an unknown key raises `ValidationError`
    (the "rejects a bad one" half of every round-trip test).
  - `frozen=True` — contracts are immutable; downstream agents evolve one with
    `model_copy(update=...)`.
- **Shared sub-models** `OptionLeg` and `PortfolioPosition` live in `common.py`
  because three contracts reuse them.
- **Enum values are pinned** and asserted member-by-member in `test_enums.py`.
  `OrderStatus` and `TriggerType` deliberately mirror the `order_status_enum` /
  `trigger_type_enum` Postgres types from migrations `0008` / `0010`, so the
  model layer and the DB layer accept the same tokens. All enums are `str`
  enums with `value == name`.
- **Cross-field validators** encode the BRD's coherence rules so a malformed
  decision can't be constructed:
  - `StrategyHypothesis` — `viable=False` requires a `rejection_reason` (BRD §16,
    an agent may reject its own family).
  - `StrategyDecision` — `SELECT_STRATEGY` requires `selected_strategy` +
    `selected_hypothesis`, and they must agree (BRD §17–§18).
  - `RiskDecision` — `REJECT` needs ≥1 violation, `MODIFY` needs ≥1 modification,
    `APPROVE` carries none (BRD §20 — the LLM can't override a deterministic
    fail).
  - `ExecutionPlan` — a multi-leg plan must use `order_class` `MLEG`/`COMBO`
    (BRD §22, legging risk).
  - `ExecutionResult` — `FILLED` can't carry `failed_legs`, `PARTIALLY_FILLED`
    must record the unfilled leg(s), `FAILED` must carry an `error` (BRD §23 —
    never falsely report success).
  - `MonitoringState` — `in_cooldown` requires `cooldown_until` (BRD §27).

## Enums (`backend/models/enums.py`)

| Enum | Members |
|---|---|
| `StrategyType` | PROTECTIVE_PUT, PUT_SPREAD, COLLAR, NO_HEDGE |
| `HedgeAction` | NEW_HEDGE, INCREASE, DECREASE, MAINTAIN, REMOVE, REPLACE, NO_TRADE |
| `DecisionType` | SELECT_STRATEGY, NO_TRADE, REASSESS |
| `RiskVerdict` | APPROVE, MODIFY, REJECT |
| `OrderStatus` | PENDING, SUBMITTED, FILLED, PARTIALLY_FILLED, CANCELLED, EXPIRED, REJECTED |
| `ExecutionStatus` | FILLED, PARTIALLY_FILLED, FAILED, CANCELLED |
| `TriggerType` | PORTFOLIO_DELTA, VOLATILITY_SPIKE, CORRELATION_BREAKDOWN, DRAWDOWN_LIMIT, TIME_ELAPSED, MANUAL |
| `OptionRight` | CALL, PUT |
| `OrderSide` | BUY, SELL |
| `AssetClass` | EQUITY, OPTION, CASH |

## Confirm (per issue)

- **#25** — `python -c "from backend.models import HedgeContext; HedgeContext.model_validate(fixture)"` → exit 0.
- **#26** — `StrategyHypothesis` and `StrategyDecision` both round-trip;
  `strategy` / `action` / `decision` reject unknown values.
- **#27** — `RiskDecision` fixture validates and round-trips (APPROVE / REJECT /
  MODIFY variants).
- **#28** — 2-leg `ExecutionPlan` validates; `ExecutionResult(status=...)` is
  enum-bound (`"DONE"` → `ValidationError`).
- **#29** — `trigger_history` is `list[TriggerObservation]` (unknown
  `trigger_type` rejected); `cooldown_until` omitted → `None`.
- **#30** — `python -c "from backend.models.enums import *; print(list(OrderStatus))"`
  → the 7-member set above, in order.

## New files

```
backend/models/__init__.py        (was empty — now re-exports every contract + enum)
backend/models/common.py          (new — Contract base, OptionLeg, PortfolioPosition)
backend/models/enums.py           (new — 10 shared str enums)
backend/models/hedge_context.py   (new — HedgeContext + 8 sub-models)
backend/models/strategy.py        (new — StrategyHypothesis, StrategyDecision, +3)
backend/models/risk.py            (new — RiskDecision, RiskCheck, RiskModification)
backend/models/execution.py       (new — ExecutionPlan, ExecutionResult, +3)
backend/models/monitoring.py      (new — MonitoringState, TriggerObservation)
tests/models/__init__.py          (new)
tests/models/test_contracts.py    (new — 5 round-trip tests)
tests/models/test_enums.py        (new — pinned members + values)
```
