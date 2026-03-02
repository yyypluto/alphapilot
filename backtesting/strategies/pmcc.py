"""
Poor Man's Covered Call (PMCC) / LEAPS Diagonal Spread strategy.

On QQQ:
- Long leg: Buy 1-year LEAPS Call at Delta ~0.80. Roll when < 90 DTE.
- Short leg: Sell 30-45 DTE Call at Delta ~0.20. Re-open upon expiration or breach.

Capital requirement is ~20-30% of underlying (the LEAPS cost).
"""

import datetime as dt
from typing import Any, Optional

from backtesting.options_pricing import BlackScholes
from backtesting.strategies.base import Strategy


class PMCCStrategy(Strategy):
    """
    PMCC: buy deep ITM LEAPS call, sell short-term OTM call against it.

    Configuration:
        leaps_dte: target DTE for LEAPS leg (default 365)
        leaps_delta: target delta for LEAPS (default 0.80)
        short_dte: target DTE for short call (default 37, midpoint of 30-45)
        short_delta: target delta for short call (default 0.20)
        roll_threshold_dte: roll LEAPS when DTE drops below this (default 90)
        num_contracts: number of contracts to trade (default 1)
    """

    def __init__(
        self,
        ticker: str = "QQQ",
        leaps_dte: int = 365,
        leaps_delta: float = 0.80,
        short_dte: int = 37,
        short_delta: float = 0.20,
        roll_threshold_dte: int = 90,
        num_contracts: int = 1,
    ):
        super().__init__(ticker=ticker, name="PMCC (LEAPS Diagonal)")
        self.leaps_dte = leaps_dte
        self.leaps_delta = leaps_delta
        self.short_dte = short_dte
        self.short_delta = short_delta
        self.roll_threshold_dte = roll_threshold_dte
        self.num_contracts = num_contracts
        self._leaps_position = None  # Track our long LEAPS
        self._short_position = None  # Track our short call
        self._last_short_open_date: Optional[dt.date] = None

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

        # ── Step 1: Manage the LEAPS leg ──
        self._manage_leaps(date, px, sigma, rfr, portfolio)

        # ── Step 2: Manage the short call leg ──
        if self._leaps_position is not None:
            self._manage_short_call(date, px, sigma, rfr, portfolio)

    def _manage_leaps(
        self, date: dt.date, px: float, sigma: float, rfr: float, portfolio: Any
    ) -> None:
        """Open or roll the LEAPS call position."""

        # Check if we need to roll (DTE below threshold)
        if self._leaps_position is not None:
            dte = self._leaps_position.days_to_expiry(date)
            if dte > self.roll_threshold_dte:
                return  # LEAPS is fine, no action needed

            # Roll: close existing LEAPS first
            T_remaining = max(dte, 1) / 365.0
            close_price = BlackScholes.call_price(
                px, self._leaps_position.strike, T_remaining, rfr, sigma
            )
            portfolio.close_option(self._leaps_position, close_price, date, reason="ROLL_LEAPS")
            self._leaps_position = None

        # Open new LEAPS if none exists
        if self._leaps_position is None:
            T = self.leaps_dte / 365.0
            strike = BlackScholes.find_strike_for_delta(
                px, T, rfr, sigma, self.leaps_delta, "call"
            )
            premium = BlackScholes.call_price(px, strike, T, rfr, sigma)

            # Check if we can afford it
            total_cost = premium * self.num_contracts * 100
            if portfolio.cash < total_cost:
                return  # Can't afford, skip

            expiration = date + dt.timedelta(days=self.leaps_dte)
            portfolio.open_option(
                self.ticker, "call", strike, expiration,
                quantity=self.num_contracts,
                premium_per_share=premium,
                date=date,
            )
            # Track the position (it's the last one added)
            self._leaps_position = portfolio.option_positions[-1]

    def _manage_short_call(
        self, date: dt.date, px: float, sigma: float, rfr: float, portfolio: Any
    ) -> None:
        """Open, roll, or close the short call leg."""

        # Check if current short call still exists
        if self._short_position is not None:
            if self._short_position not in portfolio.option_positions:
                # Was expired/assigned by the engine
                self._short_position = None

        # If we have a short call, check if it needs management
        if self._short_position is not None:
            dte = self._short_position.days_to_expiry(date)

            # Let it expire if within 3 DTE — engine handles expiration
            if dte <= 3:
                return

            # Check if breached (underlying > short strike * 0.99)
            if px >= self._short_position.strike * 0.99:
                # Close the short call (buy back)
                T_remaining = max(dte, 1) / 365.0
                close_price = BlackScholes.call_price(
                    px, self._short_position.strike, T_remaining, rfr, sigma
                )
                portfolio.close_option(
                    self._short_position, close_price, date, reason="CLOSE_BREACH"
                )
                self._short_position = None
                # Will re-open below

            else:
                return  # Short call is fine

        # Open new short call
        if self._short_position is None:
            # Minimum 5 days between short call opens to avoid churn
            if (
                self._last_short_open_date is not None
                and (date - self._last_short_open_date).days < 5
            ):
                return

            T = self.short_dte / 365.0
            strike = BlackScholes.find_strike_for_delta(
                px, T, rfr, sigma, self.short_delta, "call"
            )

            # Safety: short strike must be above LEAPS strike
            if self._leaps_position and strike <= self._leaps_position.strike:
                strike = self._leaps_position.strike + 5

            premium = BlackScholes.call_price(px, strike, T, rfr, sigma)

            if premium < 0.10:
                return  # Not worth selling

            expiration = date + dt.timedelta(days=self.short_dte)
            portfolio.open_option(
                self.ticker, "call", strike, expiration,
                quantity=-self.num_contracts,
                premium_per_share=premium,
                date=date,
            )
            self._short_position = portfolio.option_positions[-1]
            self._last_short_open_date = date
