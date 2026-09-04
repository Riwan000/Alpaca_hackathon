"""Risk-engine aggregator — task **P5-BE-7** (BRD §19–20).

The deterministic risk engine is a set of small pure checks — the P5-BE-1/2
hard limits in :mod:`~backend.agents.risk.engine` plus the P5-BE-3..6 screens in
:mod:`~backend.agents.risk.liquidity` / :mod:`~backend.agents.risk.contract` /
:mod:`~backend.agents.risk.greeks` / :mod:`~backend.agents.risk.execution`. This
module runs the whole set over one proposed
:class:`~backend.models.strategy.StrategyHypothesis` and folds the individual
:class:`~backend.agents.risk.engine.CheckOutcome` results into a single
:class:`AggregateRiskResult`:

* the **full checklist** — every check with its pass/fail and the reason behind
  it (``AggregateRiskResult.checks`` → :class:`~backend.models.risk.RiskCheck`),
  not just an overall boolean;
* an overall **verdict** — ``APPROVE`` when every hard check passes, ``REJECT``
  the moment any one fails (a deterministic ``REJECT`` the LLM Risk Agent
  (P5-BE-8) may not clear);
* **warnings** — a soft :class:`CheckOutcome` (``warning=True``, still
  ``passed``) does not block; its reason is routed to
  :attr:`AggregateRiskResult.warnings` for the Risk Agent to carry through.

The checks run in a fixed, stable order (:data:`DEFAULT_CHECKS`) so the checklist
is reproducible for the audit row and the frontend risk panel. No LLM, no I/O.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Callable, Union

from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.contract import (
    check_contract_validity,
    check_expiration_window,
)
from backend.agents.risk.engine import (
    CheckOutcome,
    RiskEngineLimits,
    check_hedge_budget,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
)
from backend.agents.risk.execution import check_price_band
from backend.agents.risk.greeks import (
    check_multileg_consistency,
    check_net_delta_bounds,
)
from backend.agents.risk.liquidity import check_buying_power, check_liquidity
from backend.models.enums import RiskVerdict
from backend.models.hedge_context import HedgeContext
from backend.models.risk import RiskCheck
from backend.models.strategy import StrategyHypothesis

__all__ = [
    "DEFAULT_CHECKS",
    "AggregateRiskResult",
    "DeterministicCheck",
    "aggregate_risk",
]

#: One deterministic check: ``(hypothesis, context, **tuning) -> CheckOutcome``
#: (or an iterable of them, when one plan-file task groups several sub-checks).
#: A check whose signature names a ``limits`` parameter (or accepts ``**kwargs``)
#: is handed the resolved :class:`RiskEngineLimits`; the rest run on their own
#: defaults.
DeterministicCheck = Callable[..., Union[CheckOutcome, Iterable[CheckOutcome]]]

#: Every deterministic hard check, in checklist order — the full P5-BE-1..6 set:
#: hedge budget (P5-BE-1); max hedge ratio / max notional / position limit
#: (P5-BE-2); buying power + liquidity (P5-BE-3); contract validity + expiration
#: window (P5-BE-4); net-delta bounds + multi-leg consistency (P5-BE-5);
#: execution price band (P5-BE-6).
DEFAULT_CHECKS: tuple[DeterministicCheck, ...] = (
    check_hedge_budget,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
    check_buying_power,
    check_liquidity,
    check_contract_validity,
    check_expiration_window,
    check_net_delta_bounds,
    check_multileg_consistency,
    check_price_band,
)


def _accepts_limits(check: DeterministicCheck) -> bool:
    """Whether ``check`` takes the aggregator's resolved ``limits`` kwarg."""
    try:
        params = inspect.signature(check).parameters
    except (TypeError, ValueError):  # builtin / C callable without a signature
        return False
    if "limits" in params:
        return True
    return any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


@dataclass(frozen=True)
class AggregateRiskResult:
    """The whole deterministic checklist plus the verdict it implies.

    ``outcomes`` is the raw per-check result in run order; the derived views
    (:attr:`checks`, :attr:`failures`, :attr:`verdict`, ...) are what callers and
    the audit row use.
    """

    cycle_id: str
    outcomes: tuple[CheckOutcome, ...]

    @property
    def checks(self) -> list[RiskCheck]:
        """The full checklist as :class:`~backend.models.risk.RiskCheck` rows.

        Every check is present — passing and failing alike — so the output is a
        checklist, not just a boolean.
        """
        return [outcome.to_risk_check() for outcome in self.outcomes]

    @property
    def failures(self) -> tuple[CheckOutcome, ...]:
        """The outcomes that hard-failed, in check order (empty when all clear)."""
        return tuple(outcome for outcome in self.outcomes if outcome.violated)

    @property
    def soft_warnings(self) -> tuple[CheckOutcome, ...]:
        """Passing outcomes that tripped a soft threshold (``warning=True``)."""
        return tuple(
            outcome
            for outcome in self.outcomes
            if getattr(outcome, "warning", False) and outcome.passed
        )

    @property
    def passed(self) -> bool:
        """``True`` only when every hard check passed (soft warnings don't block)."""
        return not self.failures

    @property
    def verdict(self) -> RiskVerdict:
        """``APPROVE`` when everything passed, ``REJECT`` on any hard fail."""
        return RiskVerdict.APPROVE if self.passed else RiskVerdict.REJECT

    @property
    def violation_codes(self) -> list[ViolationCode]:
        """The distinct :class:`ViolationCode` behind each failed check, in order."""
        return [f.code for f in self.failures if f.code is not None]

    @property
    def violations(self) -> list[str]:
        """One human-readable reason per failed check — ``"<name>: <detail>"``."""
        return [
            f"{f.name}: {f.detail}" if f.detail else f.name for f in self.failures
        ]

    @property
    def warnings(self) -> list[str]:
        """One reason per soft-warning check — ``"<name>: <detail>"``."""
        return [
            f"{w.name}: {w.detail}" if w.detail else w.name
            for w in self.soft_warnings
        ]

    def summary(self) -> str:
        """One-line tally, e.g. ``"3/4 deterministic risk checks passed"``."""
        ok = sum(1 for outcome in self.outcomes if outcome.passed)
        line = f"{ok}/{len(self.outcomes)} deterministic risk checks passed"
        soft = len(self.soft_warnings)
        if soft:
            line += f" ({soft} warning{'s' if soft != 1 else ''})"
        return line


def aggregate_risk(
    hypothesis: StrategyHypothesis,
    context: HedgeContext,
    *,
    checks: Sequence[DeterministicCheck] = DEFAULT_CHECKS,
    limits: RiskEngineLimits | None = None,
) -> AggregateRiskResult:
    """Run every deterministic check over ``hypothesis`` and fold the results.

    ``limits`` is resolved from ``context`` once and threaded through the checks
    whose signature accepts it (the P5-BE-1/2 hard limits); the P5-BE-3..6
    screens run on their own defaults. A check may return a single
    :class:`CheckOutcome` or an iterable of them; both are flattened into
    :attr:`AggregateRiskResult.outcomes` in check order.
    """
    resolved = limits or RiskEngineLimits.from_context(context)

    outcomes: list[CheckOutcome] = []
    for check in checks:
        if _accepts_limits(check):
            produced = check(hypothesis, context, limits=resolved)
        else:
            produced = check(hypothesis, context)
        if isinstance(produced, CheckOutcome):
            outcomes.append(produced)
        else:
            outcomes.extend(produced)

    return AggregateRiskResult(cycle_id=hypothesis.cycle_id, outcomes=tuple(outcomes))
