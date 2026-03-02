"""
The Wheel Strategy.

On SCHG:
- Phase 1 (Cash): Sell Cash-Secured Put, Delta ~0.25, 30-45 DTE
- Phase 2 (Assigned): If put expires ITM, take delivery of 100 shares
- Phase 3 (Holding): Sell Covered Call, Delta ~0.25, 30-45 DTE
- Phase 4 (Called Away): If call expires ITM, shares sold → back to Phase 1

The strategy cycles endlessly through these phases.
"""

import datetime as dt
from enum import Enum
from typing import Any, Optional

from backtesting.options_pricing import BlackScholes
from backtesting.strategies.base import Strategy
from backtesting.engine import OptionPosition


class WheelPhase(Enum):
    SELLING_PUT = "selling_put"
    WAITING_PUT_EXPIRY = "waiting_put_expiry"
    HOLDING_STOCK = "holding_stock"
    WAITING_CALL_EXPIRY = "waiting_call_expiry"


class WheelStrategy(Strategy):
    """
    The Wheel: Sell Put → Get Assigned → Sell Covered Call → Get Called Away → Repeat.

    Configuration:
        put_delta: target delta for CSP (default 0.25, will use -0.25)
        call_delta: target delta for covered call (default 0.25)
        dte: target days to expiry (default 37)
        num_contracts: contracts per cycle (default 1)
    """

    def __init__(
        self,
        ticker: str = "SCHG",
        put_delta: float = 0.25,
        call_delta: float = 0.25,
        dte: int = 37,
        num_contracts: int = 0,  # 0 = auto-size based on cash
    ):
        super().__init__(ticker=ticker, name=f"Wheel ({ticker})")
        self.put_delta = put_delta
        self.call_delta = call_delta
        self.dte = dte
        self.num_contracts = num_contracts
        self.phase = WheelPhase.SELLING_PUT
        self._current_option: Optional[OptionPosition] = None
        self._initial_buy_done = False

    def on_bar(
        self,
        date: dt.date,
        bar_data: dict,
        portfolio: Any,
        engine: Any,
    ) -> None:
        prices = bar_data["prices"]
        px = prices.get(self.ticker)
        if px is None or px <= 0:
            return

        sigma = bar_data["sigma"]
        rfr = bar_data["rfr"]

        # Synchronize phase with actual portfolio state
        self._sync_phase(portfolio)

        if self.phase == WheelPhase.SELLING_PUT:
            self._sell_put(date, px, sigma, rfr, portfolio)

        elif self.phase == WheelPhase.WAITING_PUT_EXPIRY:
            # Check if option still exists (engine handles expiration)
            if self._current_option not in portfolio.option_positions:
                self._current_option = None
                # Determine next phase
                if self.ticker in portfolio.stock_positions and portfolio.stock_positions[self.ticker].shares >= 100:
                    self.phase = WheelPhase.HOLDING_STOCK
                else:
                    self.phase = WheelPhase.SELLING_PUT

        elif self.phase == WheelPhase.HOLDING_STOCK:
            self._sell_covered_call(date, px, sigma, rfr, portfolio)

        elif self.phase == WheelPhase.WAITING_CALL_EXPIRY:
            if self._current_option not in portfolio.option_positions:
                self._current_option = None
                # If shares were called away
                if self.ticker not in portfolio.stock_positions or portfolio.stock_positions[self.ticker].shares < 100:
                    self.phase = WheelPhase.SELLING_PUT
                else:
                    self.phase = WheelPhase.HOLDING_STOCK

    def _sync_phase(self, portfolio: Any) -> None:
        """Synchronize internal phase with actual portfolio state."""
        has_shares = (
            self.ticker in portfolio.stock_positions
            and portfolio.stock_positions[self.ticker].shares >= 100
        )
        has_option = self._current_option in portfolio.option_positions

        if has_option:
            return  # Option still alive, keep current phase

        # Option gone → figure out what happened
        if self._current_option is not None:
            self._current_option = None

        if has_shares:
            if self.phase in (WheelPhase.SELLING_PUT, WheelPhase.WAITING_PUT_EXPIRY):
                self.phase = WheelPhase.HOLDING_STOCK
        else:
            if self.phase in (WheelPhase.HOLDING_STOCK, WheelPhase.WAITING_CALL_EXPIRY):
                self.phase = WheelPhase.SELLING_PUT

    def _sell_put(
        self, date: dt.date, px: float, sigma: float, rfr: float, portfolio: Any
    ) -> None:
        """Sell a cash-secured put."""
        T = self.dte / 365.0
        strike = BlackScholes.find_strike_for_delta(
            px, T, rfr, sigma, -self.put_delta, "put"
        )

        # Auto-size: deploy as many contracts as cash allows
        cash_per_contract = strike * 100
        if self.num_contracts > 0:
            target_contracts = self.num_contracts
        else:
            target_contracts = int(portfolio.cash / cash_per_contract)

        if target_contracts < 1:
            return

        # Leave a small cash buffer (2%)
        max_affordable = int(portfolio.cash * 0.98 / cash_per_contract)
        actual_contracts = min(target_contracts, max_affordable)
        if actual_contracts < 1:
            return

        premium = BlackScholes.put_price(px, strike, T, rfr, sigma)
        if premium < 0.05:
            return

        expiration = date + dt.timedelta(days=self.dte)
        portfolio.open_option(
            self.ticker, "put", strike, expiration,
            quantity=-actual_contracts,
            premium_per_share=premium,
            date=date,
        )
        self._current_option = portfolio.option_positions[-1]
        self.phase = WheelPhase.WAITING_PUT_EXPIRY


    def _sell_covered_call(
        self, date: dt.date, px: float, sigma: float, rfr: float, portfolio: Any
    ) -> None:
        """Sell a covered call against held shares."""
        if self.ticker not in portfolio.stock_positions:
            self.phase = WheelPhase.SELLING_PUT
            return

        shares = portfolio.stock_positions[self.ticker].shares
        contracts = shares // 100
        if contracts < 1:
            self.phase = WheelPhase.SELLING_PUT
            return

        T = self.dte / 365.0
        strike = BlackScholes.find_strike_for_delta(
            px, T, rfr, sigma, self.call_delta, "call"
        )

        premium = BlackScholes.call_price(px, strike, T, rfr, sigma)
        if premium < 0.05:
            return

        expiration = date + dt.timedelta(days=self.dte)
        portfolio.open_option(
            self.ticker, "call", strike, expiration,
            quantity=-contracts,  # Sell covered calls against ALL held shares
            premium_per_share=premium,
            date=date,
        )
        self._current_option = portfolio.option_positions[-1]
        self.phase = WheelPhase.WAITING_CALL_EXPIRY

