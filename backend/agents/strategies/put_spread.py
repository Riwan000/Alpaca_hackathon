"""Put Spread agent — task P4-BE-3 (BRD §15–16).

Long a put struck near the drawdown tolerance, short a lower-strike put that
finances part of it: bounded protection for a smaller net debit than an outright
put. The long strike is always above the short strike, and the structure's
``max_loss`` equals the net debit — both asserted against :mod:`backend.quant`.

The family is NOT_VIABLE when the book has nothing to hedge, fewer than two put
strikes trade on the name, no strike sits below the long strike to sell, or the
net debit is over budget.
"""

from __future__ import annotations

from openai import OpenAI

from backend.agents.strategies import _common as q
from backend.agents.strategies.base import SelfRejection, StrategyAgent
from backend.models.common import OptionLeg
from backend.models.enums import HedgeAction, OptionRight, OrderSide, StrategyType
from backend.models.hedge_context import HedgeContext
from backend.models.strategy import HedgeMetrics, StrategyHypothesis
from backend.quant.payoff import PayoffLeg, net_premium_cash, structure_risk
from backend.quant.risk import hedge_ratio

__all__ = ["PutSpreadAgent"]


class PutSpreadAgent(StrategyAgent):
    """Proposes a long put / short lower-put debit spread over the primary holding."""

    strategy = StrategyType.PUT_SPREAD

    def __init__(self, *, client: OpenAI | None = None) -> None:
        # See ProtectivePutAgent — deterministic, ``client`` kept for a uniform
        # call site across the four families.
        self._client = client

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        holding = q.primary_holding(context)
        if holding is None:
            raise SelfRejection("no long equity holding to protect")

        puts = q.puts_for(context, holding.symbol)
        if len({p.strike for p in puts}) < 2:
            raise SelfRejection(
                f"need two put strikes for a spread on {holding.symbol}"
            )

        contracts = q.contracts_for_shares(holding.shares)
        if contracts < 1:
            raise SelfRejection(
                f"{holding.symbol} holding is under one 100-share contract"
            )

        tolerance = context.objective.drawdown_tolerance_pct
        long_put = q.nearest_strike(puts, holding.spot * (1.0 - tolerance))

        lowers = [p for p in puts if p.strike < long_put.strike]
        if not lowers:
            raise SelfRejection("no lower-strike put to finance the spread")
        short_put = max(lowers, key=lambda p: (p.strike, -p.premium))

        mult = q.OPTION_MULTIPLIER
        cost = net_premium_cash(
            [
                (long_put.premium, contracts, mult),
                (short_put.premium, -contracts, mult),
            ]
        )
        if cost <= 0:
            raise SelfRejection(
                "long put is no richer than the short — the spread has no debit"
            )
        budget = q.hedge_budget_cash(context)
        if cost > budget:
            raise SelfRejection(
                f"put spread net debit ${cost:,.0f} is over the "
                f"${budget:,.0f} hedge budget"
            )

        legs = [
            OptionLeg(
                underlying=holding.symbol,
                right=OptionRight.PUT,
                side=OrderSide.BUY,
                strike=long_put.strike,
                expiration=long_put.expiration,
                quantity=contracts,
                limit_price=long_put.premium,
            ),
            OptionLeg(
                underlying=holding.symbol,
                right=OptionRight.PUT,
                side=OrderSide.SELL,
                strike=short_put.strike,
                expiration=short_put.expiration,
                quantity=contracts,
                limit_price=short_put.premium,
            ),
        ]

        greeks = q.combine_greeks(
            q.leg_greeks(
                spot=holding.spot,
                strike=long_put.strike,
                t=q.years_to_expiry(context, long_put.expiration),
                vol=q.resolve_volatility(long_put, context),
                right=OptionRight.PUT,
                contracts=contracts,
                side=OrderSide.BUY,
            ),
            q.leg_greeks(
                spot=holding.spot,
                strike=short_put.strike,
                t=q.years_to_expiry(context, short_put.expiration),
                vol=q.resolve_volatility(short_put, context),
                right=OptionRight.PUT,
                contracts=contracts,
                side=OrderSide.SELL,
            ),
        )

        hedge_legs = [
            PayoffLeg(
                kind="PUT", quantity=contracts, strike=long_put.strike,
                premium=long_put.premium, multiplier=mult,
            ),
            PayoffLeg(
                kind="PUT", quantity=-contracts, strike=short_put.strike,
                premium=short_put.premium, multiplier=mult,
            ),
        ]
        risk = structure_risk(hedge_legs)
        portfolio_legs = [q.underlying_leg(holding, contracts), *hedge_legs]

        width = long_put.strike - short_put.strike
        max_payout = width * contracts * mult - cost
        total_value = context.portfolio_state.total_value
        breakeven = risk.breakevens[0] if risk.breakevens else long_put.strike

        metrics = HedgeMetrics(
            hedge_ratio=hedge_ratio(
                contracts * mult * holding.spot, holding.market_value
            ),
            downside_protection_pct=min(1.0, width / holding.spot),
            cost_pct_of_portfolio=q.portfolio_fraction(cost, total_value),
            max_loss=risk.max_loss,
            breakevens=list(risk.breakevens),
            **greeks,
        )

        rationale = (
            f"Buy the {holding.symbol} {long_put.strike:g}/{short_put.strike:g} "
            f"put spread ({contracts}x) for a ${cost:,.0f} net debit — protection "
            f"runs from {long_put.strike:g} down to {short_put.strike:g}, max "
            f"payout ${max_payout:,.0f}, breakeven ~${breakeven:,.2f}."
        )

        return self.viable(
            context,
            action=HedgeAction.NEW_HEDGE,
            cost=cost,
            rationale=rationale,
            legs=legs,
            hedge_metrics=metrics,
            payoff_profile=q.payoff_points(portfolio_legs, holding.spot),
            liquidity=long_put.liquidity,
            risks=[
                f"protection stops at {short_put.strike:g}; a deeper drop is "
                "unhedged again",
                f"the ${cost:,.0f} debit is lost if {holding.symbol} holds "
                f"above {long_put.strike:g}",
            ],
            tradeoffs=[
                f"cheaper than an outright put (${cost:,.0f} net debit)",
                f"caps the payout at ${max_payout:,.0f}",
            ],
            rejection_conditions=[
                f"a move below {short_put.strike:g} becomes the base case",
                "an outright put comes into budget",
            ],
        )
