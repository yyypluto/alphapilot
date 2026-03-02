"""
Put Credit Spread strategy.

On QQQ:
- Monthly: Sell Delta 0.15 Put + Buy Put $5 lower strike.
- Max risk per spread = spread width ($5) × 100 - premium received.
- Stop-loss: close if loss reaches 2× premium received.
- Optional VIX filter: skip entry if VIX > 35.
- Position sizing: risk a fixed percentage of portfolio per trade.
"""

import datetime as dt
from typing import Any, List, Optional

from backtesting.options_pricing import BlackScholes
from backtesting.strategies.base import Strategy
from backtesting.engine import OptionPosition


class PutCreditSpreadStrategy(Strategy):
    """
    Mechanical put credit spread seller.

    Configuration:
        short_delta: delta for the short put leg (default -0.15, positive input 0.15)
        spread_width: distance between strikes in dollars (default 5)
        dte: target days to expiry (default 37)
        cycle_days: days between opening new spreads (default 30)
        risk_pct: max % of portfolio value risked per trade (default 0.05 = 5%)
        stop_loss_multiplier: close if loss reaches this × premium (default 2.0)
        vix_ceiling: skip entry if VIX exceeds this (default 35)
    """

    def __init__(
        self,
        ticker: str = "QQQ",
        short_delta: float = 0.15,
        spread_width: float = 5.0,
        dte: int = 37,
        cycle_days: int = 30,
        risk_pct: float = 0.10,
        stop_loss_multiplier: float = 2.0,
        vix_ceiling: float = 35.0,
    ):
        super().__init__(ticker=ticker, name="Put Credit Spread")
        self.short_delta = short_delta
        self.spread_width = spread_width
        self.dte = dte
        self.cycle_days = cycle_days
        self.risk_pct = risk_pct
        self.stop_loss_multiplier = stop_loss_multiplier
        self.vix_ceiling = vix_ceiling
        self._active_spreads: List[dict] = []  # Each: {short_pos, long_pos, premium_received, max_loss}
        self._last_open_date: Optional[dt.date] = None

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
        vix = bar_data["vix"]

        # ── Step 1: Check stop-loss on active spreads ──
        self._check_stop_losses(date, px, sigma, rfr, portfolio)

        # ── Step 2: Clean up expired/closed spreads ──
        self._cleanup_expired(portfolio)

        # ── Step 3: Open new spread if cycle complete ──
        self._try_open_spread(date, px, sigma, rfr, vix, portfolio)

    def _try_open_spread(
        self,
        date: dt.date,
        px: float,
        sigma: float,
        rfr: float,
        vix: float,
        portfolio: Any,
    ) -> None:
        """Open a new put credit spread if conditions met."""
        # Check cycle timing
        if self._last_open_date is not None:
            days_since = (date - self._last_open_date).days
            if days_since < self.cycle_days:
                return

        # VIX filter
        if vix > self.vix_ceiling:
            return

        T = self.dte / 365.0

        # Find short put strike (Delta ~ -0.15)
        short_strike = BlackScholes.find_strike_for_delta(
            px, T, rfr, sigma, -self.short_delta, "put"
        )

        # Long put strike = short - width
        long_strike = short_strike - self.spread_width

        if long_strike <= 0:
            return

        # Price both legs
        short_premium = BlackScholes.put_price(px, short_strike, T, rfr, sigma)
        long_premium = BlackScholes.put_price(px, long_strike, T, rfr, sigma)

        net_credit = short_premium - long_premium  # Per share
        if net_credit <= 0.05:
            return  # Not worth it

        max_loss_per_share = self.spread_width - net_credit
        max_loss_per_contract = max_loss_per_share * 100

        # Position sizing: how many contracts can we risk?
        portfolio_nav = portfolio.cash  # Use cash for sizing (conservative)
        max_risk = portfolio_nav * self.risk_pct
        num_contracts = max(1, int(max_risk / max_loss_per_contract))

        # Cap at reasonable size
        num_contracts = min(num_contracts, 20)

        expiration = date + dt.timedelta(days=self.dte)

        # Open short put (sell)
        portfolio.open_option(
            self.ticker, "put", short_strike, expiration,
            quantity=-num_contracts,
            premium_per_share=short_premium,
            date=date,
        )
        short_pos = portfolio.option_positions[-1]

        # Open long put (buy, protection)
        portfolio.open_option(
            self.ticker, "put", long_strike, expiration,
            quantity=num_contracts,
            premium_per_share=long_premium,
            date=date,
        )
        long_pos = portfolio.option_positions[-1]

        self._active_spreads.append({
            "short_pos": short_pos,
            "long_pos": long_pos,
            "premium_received": net_credit * num_contracts * 100,
            "max_loss": max_loss_per_contract * num_contracts,
            "num_contracts": num_contracts,
            "net_credit_per_share": net_credit,
        })
        self._last_open_date = date

    def _check_stop_losses(
        self, date: dt.date, px: float, sigma: float, rfr: float, portfolio: Any
    ) -> None:
        """Check if any active spread has hit stop-loss."""
        to_close = []

        for spread in self._active_spreads:
            short_pos = spread["short_pos"]
            long_pos = spread["long_pos"]

            # Skip if already closed
            if short_pos not in portfolio.option_positions:
                to_close.append(spread)
                continue

            # Compute current spread value
            dte = short_pos.days_to_expiry(date)
            if dte <= 0:
                continue  # Let engine handle expiration

            T = max(dte, 1) / 365.0
            short_price_now = BlackScholes.put_price(px, short_pos.strike, T, rfr, sigma)
            long_price_now = BlackScholes.put_price(px, long_pos.strike, T, rfr, sigma)

            # Current cost to close the spread (buy back short - sell long)
            cost_to_close = (short_price_now - long_price_now) * spread["num_contracts"] * 100
            current_loss = cost_to_close - spread["premium_received"]

            # Stop-loss check
            if current_loss > spread["premium_received"] * self.stop_loss_multiplier:
                # Close both legs
                portfolio.close_option(short_pos, short_price_now, date, reason="STOP_LOSS")
                if long_pos in portfolio.option_positions:
                    portfolio.close_option(long_pos, long_price_now, date, reason="STOP_LOSS")
                to_close.append(spread)

        for s in to_close:
            if s in self._active_spreads:
                self._active_spreads.remove(s)

    def _cleanup_expired(self, portfolio: Any) -> None:
        """Remove spreads whose positions have been handled by engine expiration."""
        to_remove = []
        for spread in self._active_spreads:
            short_gone = spread["short_pos"] not in portfolio.option_positions
            long_gone = spread["long_pos"] not in portfolio.option_positions
            if short_gone and long_gone:
                to_remove.append(spread)
        for s in to_remove:
            self._active_spreads.remove(s)
