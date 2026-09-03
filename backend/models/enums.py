"""Shared enumerations for the agent-state contracts — task P1-BE-14.

Every enum is a ``str`` enum whose value equals its member name, so the wire
form is a stable, self-describing token. Values are **pinned** here and asserted
in ``tests/models/test_enums.py`` to guard against a silent rename breaking the
DB round-trip: :class:`OrderStatus` and :class:`TriggerType` deliberately mirror
the ``order_status_enum`` / ``trigger_type_enum`` Postgres types created in the
``0008_orders`` and ``0010_monitoring_events`` migrations.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "AssetClass",
    "DecisionType",
    "ExecutionStatus",
    "HedgeAction",
    "MarketRegime",
    "OptionRight",
    "OrderSide",
    "OrderStatus",
    "RiskVerdict",
    "StrategyType",
    "TriggerType",
]


class StrategyType(str, Enum):
    """The four hedge strategy families in the MVP (BRD §15)."""

    PROTECTIVE_PUT = "PROTECTIVE_PUT"
    PUT_SPREAD = "PUT_SPREAD"
    COLLAR = "COLLAR"
    NO_HEDGE = "NO_HEDGE"


class HedgeAction(str, Enum):
    """Portfolio-level action a hypothesis or reassessment proposes.

    Covers both a fresh hedge and the adaptive-lifecycle outcomes in BRD §28
    (``MAINTAIN`` / ``INCREASE`` / ``DECREASE`` / ``REMOVE`` / ``REPLACE`` /
    ``NO_TRADE``).
    """

    NEW_HEDGE = "NEW_HEDGE"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    MAINTAIN = "MAINTAIN"
    REMOVE = "REMOVE"
    REPLACE = "REPLACE"
    NO_TRADE = "NO_TRADE"


class DecisionType(str, Enum):
    """Strategy Manager selection outcome (BRD §17 step 4)."""

    SELECT_STRATEGY = "SELECT_STRATEGY"
    NO_TRADE = "NO_TRADE"
    REASSESS = "REASSESS"


class RiskVerdict(str, Enum):
    """Risk Agent outcome (BRD §20) — the non-negotiable safety gate."""

    APPROVE = "APPROVE"
    MODIFY = "MODIFY"
    REJECT = "REJECT"


class OrderStatus(str, Enum):
    """Broker order lifecycle — mirrors ``order_status_enum`` (migration 0008)."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class ExecutionStatus(str, Enum):
    """Terminal state of an execution attempt (BRD §23)."""

    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TriggerType(str, Enum):
    """Monitoring trigger taxonomy — mirrors ``trigger_type_enum`` (migration 0010)."""

    PORTFOLIO_DELTA = "PORTFOLIO_DELTA"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    CORRELATION_BREAKDOWN = "CORRELATION_BREAKDOWN"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    TIME_ELAPSED = "TIME_ELAPSED"
    MANUAL = "MANUAL"


class MarketRegime(str, Enum):
    """Coarse market-environment classification from the Market Analysis Agent.

    The Market agent must return one of these tokens (BRD §13); a rule-based
    fallback fills one in when the LLM answer is missing or off-enum.
    """

    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"
    HIGH_VOL = "HIGH_VOL"


class OptionRight(str, Enum):
    """Option contract right."""

    CALL = "CALL"
    PUT = "PUT"


class OrderSide(str, Enum):
    """Direction of a leg or position."""

    BUY = "BUY"
    SELL = "SELL"


class AssetClass(str, Enum):
    """Coarse asset classification for a held position."""

    EQUITY = "EQUITY"
    OPTION = "OPTION"
    CASH = "CASH"
