"""Protective Put agent — task P4-BE-2 (BRD §15–16).

Buys one put per 100 covered shares of the book's largest long equity holding,
struck near the objective's drawdown tolerance. ``cost`` is the premium paid; the
payoff floor, Greeks and breakevens all come from :mod:`backend.quant`. The
family is NOT_VIABLE (a first-class :class:`SelfRejection`, never an exception the
manager has to interpret) when the book has nothing to hedge, no put trades on
the name, the holding is under one contract, or the premium blows the budget.

``hedge_metrics.max_loss`` here is the **portfolio** floor — the worst P&L of the
covered stock plus the put — so ``covered_value - max_loss`` is the protected
value the Confirm step hand-checks.
"""

from __future__ import annotations

from openai import OpenAI

from backend.agents.strategies import _common as q
from backend.agents.strategies.base import SelfRejection, StrategyAgent
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis
from backend.quant.payoff import PayoffLeg, premium_cash, structure_risk
from backend.quant.risk import hedge_ratio

__all__ = ["ProtectivePutAgent"]


class ProtectivePutAgent(StrategyAgent):
    """Proposes a long protective put over the book's primary equity holding."""

    strategy = StrategyType.PROTECTIVE_PUT

    def __init__(self, *, client: OpenAI | None = None) -> None:
        # Deterministic for now — every number is from quant/. ``client`` is
        # accepted so P4-BE-11 wires all four families through one call site and
        # the prompt templates (P4-BE-10) can slot in without a signature change.
        self._client = client

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        holding = q.primary_holding(context)
        if holding is None:
            raise SelfRejection("no long equity holding to protect")

        puts = q.puts_for(context, holding.symbol)
        if not puts:
            raise SelfRejection(f"no put candidates for {holding.symbol}")

        contracts = q.contracts_for_shares(holding.shares)
        if contracts < 1:
            raise SelfRejection(
                f"{holding.symbol} holding is under one 100-share contract"
            )

        tolerance = context.objective.drawdown_tolerance_pct
        target_strike = holding.spot * (1.0 - tolerance)
        put = q.nearest_strike(puts, target_strike)

        cost = premium_cash(put.premium, contracts, q.OPTION_MULTIPLIER)
        budget = q.hedge_budget_cash(context)
        if cost > budget:
            raise SelfRejection(
                f"protective put costs ${cost:,.0f}, over the "
                f"${budget:,.0f} hedge budget"
            )

        legs = [
            OptionLeg(
                underlying=holding.symbol,
                right=OptionRight.PUT,
                side=OrderSide.BUY,
                strike=put.strike,
                expiration=put.expiration,
                quantity=contracts,
                limit_price=put.premium,
            )
        ]

        vol = q.resolve_volatility(put, context)
        greeks = q.leg_greeks(
            spot=holding.spot,
            strike=put.strike,
            t=q.years_to_expiry(context, put.expiration),
            vol=vol,
            right=OptionRight.PUT,
            contracts=contracts,
            side=OrderSide.BUY,
        )

        payoff_legs = [
            q.underlying_leg(holding, contracts),
            PayoffLeg(
                kind="PUT",
                quantity=contracts,
                strike=put.strike,
                premium=put.premium,
                multiplier=q.OPTION_MULTIPLIER,
            ),
        ]
        risk = structure_risk(payoff_legs)

        total_value = context.portfolio_state.total_value
        covered_value = holding.spot * contracts * q.OPTION_MULTIPLIER
        floor_value = covered_value - risk.max_loss
        protection_pct = min(1.0, put.strike / holding.spot)

        metrics = HedgeMetrics(
            hedge_ratio=hedge_ratio(covered_value, holding.market_value),
            downside_protection_pct=protection_pct,
            cost_pct_of_portfolio=q.portfolio_fraction(cost, total_value),
            max_loss=risk.max_loss,
            breakevens=list(risk.breakevens),
            **greeks,
        )

        rationale = (
            f"Buy {contracts} {holding.symbol} {put.strike:g} put"
            f"{'s' if contracts > 1 else ''} expiring "
            f"{put.expiration.isoformat()} for ${cost:,.0f} "
            f"({q.portfolio_fraction(cost, total_value):.2%} of the book), "
            f"flooring the covered position near ${floor_value:,.0f} — about "
            f"{protection_pct:.0%} of its current value."
        )

        return self.viable(
            context,
            action=HedgeAction.NEW_HEDGE,
            cost=cost,
            rationale=rationale,
            legs=legs,
            hedge_metrics=metrics,
            payoff_profile=q.payoff_points(payoff_legs, holding.spot),
            liquidity=put.liquidity,
            risks=[
                f"the ${cost:,.0f} premium is a sunk cost if {holding.symbol} "
                f"stays above {put.strike:g}",
                f"protection lapses at expiry {put.expiration.isoformat()}",
            ],
            tradeoffs=[
                f"pays ${cost:,.0f} up front for a hard floor near "
                f"${put.strike:g}",
                "keeps the full upside above the strike",
            ],
            rejection_conditions=[
                f"{holding.symbol} rallies far enough that the floor is moot",
                "implied vol falls sharply, making equivalent protection "
                "cheaper to re-strike",
            ],
        )
