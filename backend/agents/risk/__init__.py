"""Risk-gate layer — Phase 5 (BRD §19–20).

The non-negotiable safety layer between the Strategy Manager and execution. The
deterministic risk engine runs pure hard-limit checks before the LLM Risk Agent
(P5-BE-8) is ever consulted:

* :mod:`~backend.agents.risk.engine` — hedge budget (P5-BE-1), position limits /
  max hedge ratio / max notional (P5-BE-2);
* :mod:`~backend.agents.risk.liquidity` — buying power + liquidity (P5-BE-3);
* :mod:`~backend.agents.risk.contract` — contract validity + expiration (P5-BE-4);
* :mod:`~backend.agents.risk.greeks` — net-delta bounds + multi-leg consistency
  (P5-BE-5);
* :mod:`~backend.agents.risk.execution` — execution-tolerance / price band
  (P5-BE-6).

A failing :class:`CheckOutcome` always carries a :class:`ViolationCode`, and the
LLM may not clear a decision that still holds one.
"""

from __future__ import annotations

from backend.agents.risk.codes import ViolationCode
from backend.agents.risk.contract import (
    DEFAULT_MIN_EXPIRY_DAYS,
    check_contract_validity,
    check_expiration_window,
)
from backend.agents.risk.engine import (
    DEFAULT_MAX_HEDGE_RATIO,
    CheckOutcome,
    RiskEngineLimits,
    check_hedge_budget,
    check_max_hedge_ratio,
    check_max_notional,
    check_position_limit,
    run_limit_checks,
)
from backend.agents.risk.execution import (
    DEFAULT_MAX_PRICE_DEVIATION_PCT,
    check_price_band,
)
from backend.agents.risk.greeks import (
    DELTA_TOLERANCE_SHARES,
    NetDeltaBounds,
    check_multileg_consistency,
    check_net_delta_bounds,
)
from backend.agents.risk.liquidity import (
    LiquidityThresholds,
    check_buying_power,
    check_liquidity,
)

__all__ = [
    "DEFAULT_MAX_HEDGE_RATIO",
    "DEFAULT_MAX_PRICE_DEVIATION_PCT",
    "DEFAULT_MIN_EXPIRY_DAYS",
    "DELTA_TOLERANCE_SHARES",
    "CheckOutcome",
    "LiquidityThresholds",
    "NetDeltaBounds",
    "RiskEngineLimits",
    "ViolationCode",
    "check_buying_power",
    "check_contract_validity",
    "check_expiration_window",
    "check_hedge_budget",
    "check_liquidity",
    "check_max_hedge_ratio",
    "check_max_notional",
    "check_multileg_consistency",
    "check_net_delta_bounds",
    "check_position_limit",
    "check_price_band",
    "run_limit_checks",
]
