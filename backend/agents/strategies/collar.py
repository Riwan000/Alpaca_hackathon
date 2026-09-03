"""Collar agent — task P4-BE-4 (BRD §15–16).

Long a put near the drawdown tolerance, short an out-of-the-money call whose
premium pays for most (or all) of it: a near-zero-cost floor bought by giving up
the upside above the call strike. The net can be a small debit or a credit; the
call strike is recorded as the upside cap in the tradeoffs and the rationale.

The family is NOT_VIABLE when the book has nothing to hedge, no put or no call
trades on the name, the holding is under one contract, or the collar still costs
more than the hedge budget.
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

__all__ = ["CollarAgent"]


class CollarAgent(StrategyAgent):
    """Proposes a long put / short OTM call collar over the primary holding."""

    strategy = StrategyType.COLLAR

    def __init__(self, *, client: OpenAI | None = None) -> None:
        # See ProtectivePutAgent — deterministic, ``client`` kept for a uniform
        # call site across the four families.
        self._client = client

    def build(self, context: HedgeContext) -> StrategyHypothesis:
        holding = q.primary_holding(context)
        if holding is None:
            raise SelfRejection("no long equity holding to protect")

        puts = q.puts_for(context, holding.symbol)
        if not puts:
            raise SelfRejection(f"no put candidates for {holding.symbol}")
        calls = q.calls_for(context, holding.symbol)
        if not calls:
            raise SelfRejection(
                f"no call candidates to finance a collar on {holding.symbol}"
            )

        contracts = q.contracts_for_shares(holding.shares)
        if contracts < 1:
            raise SelfRejection(
                f"{holding.symbol} holding is under one 100-share contract"
            )

        tolerance = context.objective.drawdown_tolerance_pct
        long_put = q.nearest_strike(puts, holding.spot * (1.0 - tolerance))

        # Prefer an OTM call (keeps some upside); among those pick the premium
        # that best offsets the put, tie-breaking toward the higher cap.
        otm_calls = [c for c in calls if c.strike >= holding.spot] or calls
        short_call = min(
            otm_calls, key=lambda c: (abs(c.premium - long_put.premium), -c.strike)
        )

        mult = q.OPTION_MULTIPLIER
        net = net_premium_cash(
            [
                (long_put.premium, contracts, mult),
                (short_call.premium, -contracts, mult),
            ]
        )
        budget = q.hedge_budget_cash(context)
        if net > budget:
            raise SelfRejection(
                f"collar still costs ${net:,.0f}, over the ${budget:,.0f} "
                "hedge budget"
            )
        cost = max(0.0, net)
        credited = net < 0.0
        net_word = "credit" if credited else "debit"

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
                right=OptionRight.CALL,
                side=OrderSide.SELL,
                strike=short_call.strike,
                expiration=short_call.expiration,
                quantity=contracts,
                limit_price=short_call.premium,
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
                strike=short_call.strike,
                t=q.years_to_expiry(context, short_call.expiration),
                vol=q.resolve_volatility(short_call, context),
                right=OptionRight.CALL,
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
                kind="CALL", quantity=-contracts, strike=short_call.strike,
                premium=short_call.premium, multiplier=mult,
            ),
        ]
        portfolio_legs = [q.underlying_leg(holding, contracts), *hedge_legs]
        risk = structure_risk(portfolio_legs)
        total_value = context.portfolio_state.total_value

        metrics = HedgeMetrics(
            hedge_ratio=hedge_ratio(
                contracts * mult * holding.spot, holding.market_value
            ),
            downside_protection_pct=min(1.0, long_put.strike / holding.spot),
            cost_pct_of_portfolio=q.portfolio_fraction(cost, total_value),
            max_loss=risk.max_loss,
            breakevens=list(risk.breakevens),
            **greeks,
        )

        rationale = (
            f"Collar {holding.symbol} ({contracts}x): long the "
            f"{long_put.strike:g} put, short the {short_call.strike:g} call, for "
            f"a net {net_word} of ${abs(net):,.0f}. Floors near "
            f"${long_put.strike:g}; upside capped at ${short_call.strike:g}."
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
                f"gains above {short_call.strike:g} are forgone to the short call",
                f"assignment on the short call if {holding.symbol} rallies "
                "through the cap",
            ],
            tradeoffs=[
                f"near-zero outlay (net {net_word} ${abs(net):,.0f})",
                f"upside capped at {short_call.strike:g} by the short call",
            ],
            rejection_conditions=[
                f"{holding.symbol} approaches {short_call.strike:g} and the cap "
                "starts to bite",
                "a cheaper put makes an uncapped hedge affordable",
            ],
        )
