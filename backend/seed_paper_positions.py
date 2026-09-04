"""One-off: buy a small equity position in the Alpaca **paper** account.

The real orchestrator cycle (``POST /run-cycle``) correctly returns NO_HEDGE
when the paper account holds no equity — there's nothing to protect. This
script gives it something to protect, by submitting real (paper-money) market
buy orders for a couple of names via the same :class:`AlpacaClient` the
orchestrator uses.

This is a genuine trade against the Alpaca paper API (simulated money, real
account state) — run it yourself rather than having an agent run it for you:

    python -m backend.seed_paper_positions
    python -m backend.seed_paper_positions --symbol AAPL --qty 10 --symbol MSFT --qty 5
"""

from __future__ import annotations

import argparse
import time
from typing import NamedTuple

from backend.integrations.alpaca.client import AlpacaClient, AlpacaError

_DEFAULT_ORDERS: tuple[tuple[str, int], ...] = (("AAPL", 10), ("MSFT", 5))
_FILL_POLL_ATTEMPTS = 5
_FILL_POLL_DELAY_SECONDS = 1.0


class _Leg(NamedTuple):
    symbol: str
    qty: int


def _parse_args(argv: list[str] | None = None) -> list[_Leg]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbol", action="append", dest="symbols", default=[], help="ticker to buy (repeatable)"
    )
    parser.add_argument(
        "--qty", action="append", dest="qtys", type=int, default=[], help="shares for the matching --symbol"
    )
    args = parser.parse_args(argv)

    if not args.symbols:
        return [_Leg(symbol, qty) for symbol, qty in _DEFAULT_ORDERS]

    if len(args.symbols) != len(args.qtys):
        parser.error("--symbol and --qty must be paired one-to-one and given the same number of times")
    return [_Leg(symbol.upper(), qty) for symbol, qty in zip(args.symbols, args.qtys)]


def _buy(client: AlpacaClient, leg: _Leg) -> dict:
    payload = {
        "symbol": leg.symbol,
        "qty": str(leg.qty),
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }
    return client.submit_order(payload)


def main(argv: list[str] | None = None) -> None:
    legs = _parse_args(argv)

    with AlpacaClient() as client:
        if not client.paper:
            raise SystemExit(
                "ALPACA_PAPER is not true — refusing to submit orders against a live account."
            )

        account = client.get_account()
        print(f"Paper account {account.get('account_number')}: cash=${account.get('cash')}")

        submitted = []
        for leg in legs:
            try:
                order = _buy(client, leg)
            except AlpacaError as exc:
                print(f"  FAILED to submit {leg.qty} {leg.symbol}: {exc}")
                continue
            print(f"  submitted order {order.get('id')}: buy {leg.qty} {leg.symbol}")
            submitted.append(order)

        if not submitted:
            raise SystemExit("No orders were accepted — see failures above.")

        # Market orders fill almost immediately in the paper sandbox; give the
        # broker a few seconds before reading positions back.
        for _ in range(_FILL_POLL_ATTEMPTS):
            time.sleep(_FILL_POLL_DELAY_SECONDS)
            positions = client.get_positions()
            if len(positions) >= len(submitted):
                break

        print("\nCurrent paper positions:")
        for position in client.get_positions():
            print(
                f"  {position.get('symbol')}: {position.get('qty')} shares "
                f"@ avg ${position.get('avg_entry_price')}"
            )


if __name__ == "__main__":
    main()
