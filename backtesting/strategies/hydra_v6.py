"""
Hydra V6 ETF Rotation Strategy.

Ported from the standalone backtest.py into the backtesting framework.

Three-state machine:
  State 0 — Attack:  100% QLD (2x leveraged Nasdaq)
  State 1 — Defense: 100% QQQ (de-leverage)
  State 2 — Escape:  20% GLD + Cash + Ladder-buy QQQ on deep dips

State transitions are based on:
  - QQQ vs 200-day MA (trend)
  - QQQ 60-day rolling drawdown
  - SOXX 60-day rolling drawdown (chip divergence signal)
"""

import datetime as dt
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from backtesting.strategies.base import Strategy


class HydraV6Strategy(Strategy):
    """
    V6 Hydra ETF Rotation Strategy.

    Rotates between QLD (attack), QQQ (defense), and GLD+Cash (escape)
    based on a three-state machine driven by trend and momentum indicators.
    """

    # Tickers used (must be present in data)
    TICKER_QQQ = "QQQ"
    TICKER_QLD = "QLD"
    TICKER_GLD = "GLD"
    TICKER_SOXX = "SOXX"

    def __init__(
        self,
        ticker: str = "QQQ",
        lookback: int = 60,
        ma_period: int = 200,
        dd_defense: float = -0.04,
        dd_escape_qqq: float = -0.04,
        dd_escape_soxx: float = -0.10,
        dd_soft_qqq: float = -0.02,
        dd_soft_soxx: float = -0.05,
        gld_weight: float = 0.20,
        ladder_thresholds: Optional[Dict[float, float]] = None,
        use_soxx: bool = True,
        cash_return: float = 0.03,
    ):
        super().__init__(ticker=ticker, name="Hydra V6 ETF Rotation")

        self.lookback = lookback
        self.ma_period = ma_period
        self.dd_defense = dd_defense
        self.dd_escape_qqq = dd_escape_qqq
        self.dd_escape_soxx = dd_escape_soxx
        self.dd_soft_qqq = dd_soft_qqq
        self.dd_soft_soxx = dd_soft_soxx
        self.gld_weight = gld_weight
        self.use_soxx = use_soxx
        self.cash_return = cash_return

        # Ladder buy thresholds: dd_level → allocation %
        self.ladder_thresholds = ladder_thresholds or {
            -0.30: 0.80,
            -0.20: 0.50,
            -0.10: 0.20,
        }

        # Internal state tracking
        self._history_qqq: list = []
        self._history_soxx: list = []
        self._prev_state: Optional[int] = None

    def _compute_indicators(self) -> Dict[str, float]:
        """Compute MA200, drawdowns from internal price history."""
        result = {}

        qqq_arr = np.array(self._history_qqq)

        # MA200
        if len(qqq_arr) >= self.ma_period:
            result["ma200"] = float(np.mean(qqq_arr[-self.ma_period:]))
        else:
            result["ma200"] = float(np.mean(qqq_arr)) if len(qqq_arr) > 0 else 0.0

        # QQQ rolling drawdown
        if len(qqq_arr) >= self.lookback:
            window = qqq_arr[-self.lookback:]
            roll_max = np.max(window)
            result["dd_qqq"] = float((qqq_arr[-1] - roll_max) / roll_max) if roll_max > 0 else 0.0
        else:
            result["dd_qqq"] = 0.0

        # SOXX rolling drawdown
        if self.use_soxx and len(self._history_soxx) >= self.lookback:
            soxx_arr = np.array(self._history_soxx)
            window = soxx_arr[-self.lookback:]
            roll_max = np.max(window)
            result["dd_soxx"] = float((soxx_arr[-1] - roll_max) / roll_max) if roll_max > 0 else 0.0
        else:
            result["dd_soxx"] = 0.0

        return result

    def _determine_state(self, px_qqq: float, indicators: Dict[str, float]) -> int:
        """
        Determine current market state.

        Returns:
            0 = Attack (QLD), 1 = Defense (QQQ), 2 = Escape (GLD+Cash)
        """
        ma200 = indicators["ma200"]
        dd_qqq = indicators["dd_qqq"]
        dd_soxx = indicators["dd_soxx"]

        # Priority order (matching np.select logic from backtest.py):
        # 1. QQQ < MA200 → Escape
        if px_qqq < ma200:
            return 2

        # 2. QQQ drawdown > threshold → Defense
        if dd_qqq < self.dd_defense:
            return 1

        if self.use_soxx:
            # 3. Mild QQQ dd + severe SOXX dd → Escape
            if dd_qqq > self.dd_escape_qqq and dd_soxx < self.dd_escape_soxx:
                return 2
            # 4. Very mild QQQ dd + moderate SOXX dd → Defense
            if dd_qqq > self.dd_soft_qqq and dd_soxx < self.dd_soft_soxx:
                return 1

        # Default → Attack
        return 0

    def _compute_allocation(self, state: int, dd_qqq: float) -> Dict[str, float]:
        """
        Compute target allocation weights.

        Returns dict: {ticker: weight} where weights sum to 1.0.
        """
        if state == 0:
            return {self.TICKER_QLD: 1.0}
        elif state == 1:
            return {self.TICKER_QQQ: 1.0}
        else:
            # State 2: Escape — GLD base + ladder buy
            dip_allocation = 0.0
            for threshold, alloc in sorted(self.ladder_thresholds.items()):
                if dd_qqq < threshold:
                    dip_allocation = alloc

            weights = {}
            if dip_allocation > 0:
                weights[self.TICKER_QQQ] = dip_allocation
            weights[self.TICKER_GLD] = self.gld_weight
            cash_weight = 1.0 - sum(weights.values())
            if cash_weight > 0.001:
                weights["CASH"] = cash_weight
            return weights

    def on_bar(
        self,
        date: dt.date,
        bar_data: dict,
        portfolio: Any,
        engine: Any,
    ) -> None:
        prices = bar_data["prices"]
        px_qqq = prices.get(self.TICKER_QQQ)

        if px_qqq is None or px_qqq <= 0:
            return

        # Accumulate history
        self._history_qqq.append(px_qqq)
        soxx_px = prices.get(self.TICKER_SOXX)
        if soxx_px is not None:
            self._history_soxx.append(soxx_px)

        # Need at least some history for MA
        if len(self._history_qqq) < 30:
            # Early days: just buy QQQ as default
            if not portfolio.stock_positions:
                shares = int(portfolio.cash // px_qqq)
                if shares > 0:
                    portfolio.buy_stock(self.TICKER_QQQ, shares, px_qqq, date)
            return

        # Compute indicators
        indicators = self._compute_indicators()
        state = self._determine_state(px_qqq, indicators)

        # Compute target allocation
        target = self._compute_allocation(state, indicators["dd_qqq"])

        # Rebalance if state changed
        if state != self._prev_state:
            nav = portfolio.nav(prices, bar_data["rfr"], bar_data["sigma_map"], date)

            # Sell all current stock positions
            for ticker in list(portfolio.stock_positions.keys()):
                pos = portfolio.stock_positions[ticker]
                px = prices.get(ticker, pos.cost_basis)
                portfolio.sell_stock(ticker, pos.shares, px, date)

            # Buy new target allocation
            for ticker, weight in target.items():
                if ticker == "CASH":
                    continue
                px = prices.get(ticker)
                if px is None or px <= 0:
                    continue
                target_value = nav * weight
                shares = int(target_value // px)
                if shares > 0:
                    portfolio.buy_stock(ticker, shares, px, date)

        self._prev_state = state
