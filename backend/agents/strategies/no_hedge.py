"""No-Hedge agent — task P4-BE-5 (BRD §15–16).

The always-available alternative: propose doing nothing and say why in terms of
the current drawdown against the objective's tolerance. It never rejects its own
family — an unhedged book is always a real option the Strategy Manager must
weigh — so :meth:`build` returns a VIABLE hypothesis on every context, including
an empty one.
"""

from __future__ import annotations

from openai import OpenAI

from backend.agents.strategies.base import StrategyAgent
from backend.models.enums import HedgeAction, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis

__all__ = ["NoHedgeAgent"]


class NoHedgeAgent(StrategyAgent):
    """Proposes leaving the book unhedged, reasoned from drawdown vs tolerance."""

    strategy = StrategyType.NO_HEDGE

    def __init__(self, *, client: OpenAI | None = None) -> None:
        # See ProtectivePutAgent — deterministic, ``client`` kept for a uniform
        # call site across the four families.
        self._client = client

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        state = context.portfolio_state
        drawdown = abs(state.drawdown) if state.drawdown is not None else 0.0
        tolerance = context.objective.drawdown_tolerance_pct
        within = drawdown <= tolerance
        exposure = (
            state.gross_exposure
            if state.gross_exposure is not None
            else state.equity
        )

        if within:
            tail = (
                "Staying unhedged keeps the full upside and avoids paying option "
                "premium; revisit if the selloff deepens."
            )
        else:
            tail = (
                "A hedge here would lock in the loss — hold the book and "
                "reassess on the next cycle."
            )
        rationale = (
            f"Current drawdown {drawdown:.1%} is "
            f"{'within' if within else 'beyond'} the {tolerance:.1%} drawdown "
            f"tolerance. {tail}"
        )

        metrics = HedgeMetrics(
            hedge_ratio=0.0,
            downside_protection_pct=0.0,
            cost_pct_of_portfolio=0.0,
            max_loss=exposure,
        )

        return self.viable(
            context,
            action=HedgeAction.NO_TRADE,
            cost=0.0,
            rationale=rationale,
            hedge_metrics=metrics,
            risks=[
                f"the book's full downside (~${exposure:,.0f}) is unprotected",
            ],
            tradeoffs=[
                "zero cost and full upside",
                "no floor if the drawdown runs past tolerance",
            ],
            rejection_conditions=[
                f"drawdown exceeds the {tolerance:.0%} tolerance",
                "realised volatility spikes or the regime flips to RISK_OFF",
            ],
        )
