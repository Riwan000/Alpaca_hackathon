"""Deterministic risk metrics — Phase 2 (tasks P2-BE-5 … P2-BE-8).

Pure functions over in-memory return series and notionals: no LLM, no I/O.
Volatility, beta and correlation share the sample-moment helpers in
:mod:`backend.quant.risk._stats`; hedge ratio works off raw notionals.
"""

from __future__ import annotations

from backend.quant.risk.beta import (
    BetaResult,
    beta,
    compute_beta,
    portfolio_beta,
)
from backend.quant.risk.correlation import (
    CorrelationMatrix,
    correlation,
    correlation_matrix,
)
from backend.quant.risk.hedge_ratio import (
    HedgeAssessment,
    assess_hedge,
    hedge_drift,
    hedge_ratio,
    rebalance_notional,
)
from backend.quant.risk.volatility import (
    DEFAULT_PERIODS_PER_YEAR,
    VolatilityResult,
    annualize,
    covariance_matrix,
    portfolio_volatility,
    returns_volatility,
    volatility,
)

__all__ = [
    # volatility
    "DEFAULT_PERIODS_PER_YEAR",
    "VolatilityResult",
    "annualize",
    "returns_volatility",
    "volatility",
    "covariance_matrix",
    "portfolio_volatility",
    # beta
    "BetaResult",
    "compute_beta",
    "beta",
    "portfolio_beta",
    # correlation
    "CorrelationMatrix",
    "correlation",
    "correlation_matrix",
    # hedge ratio
    "HedgeAssessment",
    "hedge_ratio",
    "hedge_drift",
    "rebalance_notional",
    "assess_hedge",
]
