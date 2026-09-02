# ADR 0001 — Risk-metric storage in Phase 2

- **Status:** Accepted
- **Date:** 2026-09-03
- **Task:** P2-DB-2 (Phase 2 — Deterministic quant engine, track `db`)
- **Deciders:** this workspace (backend/DB/ops)

## Context

P2-DB-2 asks whether computed **risk metrics** (volatility, beta, correlation,
drawdown, concentration, hedge ratio …) need storage beyond the portfolio
snapshot, and to add a dedicated `risk_metrics` migration only if so.

Facts that bear on the decision:

- The Phase 2 quant engine (`backend/quant/**`, tasks P2-BE-1..23) is specified
  as **pure functions — no LLM, no I/O**. It computes; it does not persist.
- The only Phase 2 persistence is the optional snapshot round-trip in P2-DB-1
  (`compute → repo.save → read back`), which targets `portfolio_snapshots`.
- The phased plan already routes portfolio-level risk metrics onto the snapshot:
  **P3-DB-3** — "Persist computed risk metrics alongside the snapshot" — whose
  confirm step is `select volatility, beta, drawdown from portfolio_snapshots
  order by ts desc limit 1`.
- Per-cycle risk-gate output already has a home: the `risk_checks` table
  (migration `0007_risk_checks`) with jsonb `checks / violations / warnings /
  modifications`. `risk_metrics` in `docs/…_Tech_Stack.md` is a **field of the
  `RiskDecision` contract**, carried in that jsonb payload — not a table.

## Decision

**Do not add a `risk_metrics` table or migration in Phase 2.**

- Portfolio-level risk metrics will be stored as **numeric columns on
  `portfolio_snapshots`**, added by a migration in Phase 3 when P3-DB-3 needs
  them. One row per analysis cycle already exists there; the metrics are 1:1
  with that row.
- Risk-gate metrics for a specific hedge decision travel inside the
  `RiskDecision` payload persisted to `risk_checks` jsonb columns.
- No `tests/db/test_schema.py::test_risk_metrics` is added. Per the P2-DB-2 test
  line ("if added … ; else the decision is recorded"), **this ADR is the
  recorded decision.**

## Rationale

- **YAGNI.** A separate normalized table adds a migration and a join for a
  read the hackathon MVP never issues. The snapshot is the natural key.
- **Locality.** Every consumer (dashboard `RiskOverview`, strategy layer,
  monitoring triggers) reads risk metrics *with* the snapshot they describe.
  Columns on `portfolio_snapshots` keep that a single-row read.
- **Reversible.** Columns can be added in Phase 3 without touching Phase 2.

## Consequences

- Phase 3 must extend `portfolio_snapshots` (new migration) with the metric
  columns rather than creating a new table — see P3-DB-3.
- The `PortfolioSnapshotRecord` / `PortfolioSnapshotRepository` seam
  (`backend/db/repository.py`, P2-DB-1) will gain the metric fields at that
  point.

## Revisit if

We need time-series risk metrics decoupled from snapshots — e.g. intraday
recompute without writing a full snapshot, or metrics at a cadence finer than
the analysis cycle. Then introduce a dedicated table keyed by
`(cycle_id, ts, metric_name)` and migrate the snapshot columns into it.
