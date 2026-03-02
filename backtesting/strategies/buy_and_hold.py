"""
Buy & Hold benchmark strategy.

Invests 100% of capital into the target ticker on day 1 and holds.
Used for apples-to-apples comparison with options strategies.
"""

import datetime as dt
from typing import Any

from backtesting.strategies.base import Strategy


class BuyAndHoldStrategy(Strategy):
    """Buy & Hold benchmark: buy on day 1, never sell."""

    def __init__(self, ticker: str = "QQQ"):
        super().__init__(ticker=ticker, name=f"Buy & Hold {ticker}")
        self._entered = False

    def on_bar(
        self,
        date: dt.date,
        bar_data: dict,
        portfolio: Any,
        engine: Any,
    ) -> None:
        if self._entered:
            return

        prices = bar_data["prices"]
        px = prices.get(self.ticker)
        if px is None or px <= 0:
            return

        # Buy as many shares as we can with available cash
        shares = int(portfolio.cash // px)
        if shares > 0:
            portfolio.buy_stock(self.ticker, shares, px, date)
            self._entered = True
