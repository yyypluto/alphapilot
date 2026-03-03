"""
Hydra + PMCC Combined Strategy.

Combines the V6 Hydra state machine (attack/defense/escape) with PMCC for the attack phase:
- State 0 (Attack): PMCC on QQQ — buy LEAPS call (Delta 0.80) + sell short OTM call (Delta 0.20)
- State 1 (Defense): Hold QQQ directly
- State 2 (Escape): GLD + Cash + ladder dip-buy

Supports two state machine variants:
- "soxx": Full V6 Hydra with SOXX divergence signals (original backtest.py logic)
- "simple": Simplified version using only QQQ MA200 + drawdown thresholds
"""

import datetime as dt
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

from backtesting.options_pricing import BlackScholes
from backtesting.strategies.base import Strategy
from backtesting.engine import OptionPosition


class HydraPMCCStrategy(Strategy):
    """
    Hydra State Machine + PMCC for Attack mode.

    Args:
        state_mode: "soxx" for full V6 (SOXX divergence), "simple" for QQQ-only
    """

    def __init__(
        self,
        ticker: str = "QQQ",
        state_mode: Literal["soxx", "simple"] = "soxx",
        # PMCC params
        leaps_dte: int = 365,
        leaps_delta: float = 0.80,
        short_dte: int = 37,
        short_delta: float = 0.20,
        roll_threshold_dte: int = 90,
        # State machine params
        dd_window: int = 60,
        ma_window: int = 200,
        # Circuit breaker: SOXX crash → force escape regardless of QQQ
        soxx_circuit_breaker: float = -0.15,
        # Cooldown: minimum days to hold a state before allowing switch
        cooldown_days: int = 5,
    ):
        label = "Hydra(SOXX) + PMCC" if state_mode == "soxx" else "Hydra(Simple) + PMCC"
        super().__init__(ticker=ticker, name=label)
        self.state_mode = state_mode
        self.leaps_dte = leaps_dte
        self.leaps_delta = leaps_delta
        self.short_dte = short_dte
        self.short_delta = short_delta
        self.roll_threshold_dte = roll_threshold_dte
        self.dd_window = dd_window
        self.soxx_circuit_breaker = soxx_circuit_breaker
        self.cooldown_days = cooldown_days
        self.ma_window = ma_window

        # PMCC tracking
        self._leaps_position: Optional[OptionPosition] = None
        self._short_position: Optional[OptionPosition] = None
        self._last_short_open: Optional[dt.date] = None

        # State tracking
        self._current_state = -1  # uninitialized
        self._last_switch_date: Optional[dt.date] = None
        self._qqq_history: list = []
        self._soxx_history: list = []

    # ─────────────────────────────────────────────────────────
    # State Machine
    # ─────────────────────────────────────────────────────────

    def _compute_state(self, prices: dict) -> int:
        """
        Determine market state.

        SOXX mode (full V6 Hydra):
            Priority order (np.select):
            1. QQQ < MA200                              → State 2 (Escape)
            2. DD_QQQ < -4%                             → State 1 (Defense)
            3. DD_QQQ > -4% AND DD_SOXX < -10%          → State 2 (Escape, divergence!)
            4. DD_QQQ > -2% AND DD_SOXX < -5%           → State 1 (Defense, early warning)
            5. Default                                  → State 0 (Attack)

        Simple mode:
            1. QQQ < MA200                              → State 2
            2. DD_QQQ < -2%                             → State 1
            3. Default                                  → State 0
        """
        px_qqq = prices.get("QQQ")
        if px_qqq is None:
            return self._current_state if self._current_state >= 0 else 0

        self._qqq_history.append(px_qqq)

        # Need enough data for MA200
        if len(self._qqq_history) < self.ma_window:
            return 0

        # Compute QQQ indicators
        ma200 = np.mean(self._qqq_history[-self.ma_window:])
        qqq_recent = self._qqq_history[-self.dd_window:] if len(self._qqq_history) >= self.dd_window else self._qqq_history
        qqq_roll_max = max(qqq_recent)
        dd_qqq = (px_qqq - qqq_roll_max) / qqq_roll_max if qqq_roll_max > 0 else 0

        if self.state_mode == "soxx":
            return self._compute_state_soxx(px_qqq, ma200, dd_qqq, prices)
        else:
            return self._compute_state_simple(px_qqq, ma200, dd_qqq)

    def _compute_state_soxx(
        self, px_qqq: float, ma200: float, dd_qqq: float, prices: dict
    ) -> int:
        """Full V6 Hydra with SOXX divergence — exact replica of backtest.py."""
        px_soxx = prices.get("SOXX")
        if px_soxx is not None:
            self._soxx_history.append(px_soxx)

        # Compute SOXX drawdown
        dd_soxx = None
        if len(self._soxx_history) >= self.dd_window:
            soxx_recent = self._soxx_history[-self.dd_window:]
            soxx_roll_max = max(soxx_recent)
            dd_soxx = (self._soxx_history[-1] - soxx_roll_max) / soxx_roll_max if soxx_roll_max > 0 else 0

        # Priority-ordered conditions
        # 0. CIRCUIT BREAKER: SOXX disaster → force Escape no matter what
        if dd_soxx is not None and dd_soxx < self.soxx_circuit_breaker:
            return 2

        # 1. QQQ below MA200 → Escape
        if px_qqq < ma200:
            return 2

        # 2. QQQ drawdown > 4% → Defense
        if dd_qqq < -0.04:
            return 1

        # 3. QQQ drawdown mild BUT SOXX crashed > 10% → Escape (divergence!)
        if dd_soxx is not None and dd_qqq > -0.04 and dd_soxx < -0.10:
            return 2

        # 4. QQQ barely dipping BUT SOXX down > 5% → Defense (early warning)
        if dd_soxx is not None and dd_qqq > -0.02 and dd_soxx < -0.05:
            return 1

        # 5. Default → Attack
        return 0

    def _compute_state_simple(
        self, px_qqq: float, ma200: float, dd_qqq: float
    ) -> int:
        """Simplified: QQQ-only signals."""
        if px_qqq < ma200:
            return 2
        if dd_qqq < -0.02:
            return 1
        return 0

    # ─────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────

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

        new_state = self._compute_state(prices)

        # State transition with cooldown
        if new_state != self._current_state:
            # Cooldown check: skip switch if not enough days since last switch
            # EXCEPTION: escalation to State 2 (escape) always allowed
            if self._last_switch_date is not None and self.cooldown_days > 0:
                days_since = (date - self._last_switch_date).days
                is_escalation = (new_state == 2)
                if days_since < self.cooldown_days and not is_escalation:
                    new_state = self._current_state  # Suppress the switch

        if new_state != self._current_state:
            old_state = self._current_state
            self._current_state = new_state
            self._last_switch_date = date

            if old_state == 0 and new_state != 0:
                self._close_pmcc(date, px, sigma, rfr, portfolio)
            if old_state == 1 and new_state != 1:
                if self.ticker in portfolio.stock_positions:
                    shares = portfolio.stock_positions[self.ticker].shares
                    if shares > 0:
                        portfolio.sell_stock(self.ticker, shares, px, date)
            if old_state == 2 and new_state != 2:
                if "GLD" in portfolio.stock_positions:
                    gld_shares = portfolio.stock_positions["GLD"].shares
                    gld_px = prices.get("GLD", 0)
                    if gld_shares > 0 and gld_px > 0:
                        portfolio.sell_stock("GLD", gld_shares, gld_px, date)
                # Also sell any dip-bought QQQ when leaving escape
                if new_state == 0 and self.ticker in portfolio.stock_positions:
                    shares = portfolio.stock_positions[self.ticker].shares
                    if shares > 0:
                        portfolio.sell_stock(self.ticker, shares, px, date)

        if self._current_state == 0:
            self._run_pmcc(date, px, sigma, rfr, portfolio)
        elif self._current_state == 1:
            self._run_defense(date, px, portfolio)
        elif self._current_state == 2:
            self._run_escape(date, prices, portfolio)

    # ─────────────────────────────────────────────────────────
    # State 0: PMCC Attack
    # ─────────────────────────────────────────────────────────

    def _run_pmcc(self, date, px, sigma, rfr, portfolio):
        self._manage_leaps(date, px, sigma, rfr, portfolio)
        if self._leaps_position is not None:
            self._manage_short_call(date, px, sigma, rfr, portfolio)

    def _manage_leaps(self, date, px, sigma, rfr, portfolio):
        if self._leaps_position is not None:
            if self._leaps_position not in portfolio.option_positions:
                self._leaps_position = None
            else:
                dte = self._leaps_position.days_to_expiry(date)
                if dte > self.roll_threshold_dte:
                    return
                T = max(dte, 1) / 365.0
                close_price = BlackScholes.call_price(px, self._leaps_position.strike, T, rfr, sigma)
                portfolio.close_option(self._leaps_position, close_price, date, "ROLL_LEAPS")
                self._leaps_position = None

        if self._leaps_position is None:
            T = self.leaps_dte / 365.0
            strike = BlackScholes.find_strike_for_delta(px, T, rfr, sigma, self.leaps_delta, "call")
            premium = BlackScholes.call_price(px, strike, T, rfr, sigma)

            max_spend = portfolio.cash * 0.70
            num_contracts = max(1, int(max_spend / (premium * 100)))
            total_cost = premium * num_contracts * 100
            if portfolio.cash < total_cost:
                num_contracts = max(1, int(portfolio.cash / (premium * 100)))
                if premium * num_contracts * 100 > portfolio.cash:
                    return

            expiration = date + dt.timedelta(days=self.leaps_dte)
            portfolio.open_option(
                self.ticker, "call", strike, expiration,
                quantity=num_contracts, premium_per_share=premium, date=date,
            )
            self._leaps_position = portfolio.option_positions[-1]

    def _manage_short_call(self, date, px, sigma, rfr, portfolio):
        if self._short_position is not None:
            if self._short_position not in portfolio.option_positions:
                self._short_position = None

        if self._short_position is not None:
            dte = self._short_position.days_to_expiry(date)
            if dte <= 3:
                return
            if px >= self._short_position.strike * 0.99:
                T = max(dte, 1) / 365.0
                close_price = BlackScholes.call_price(px, self._short_position.strike, T, rfr, sigma)
                portfolio.close_option(self._short_position, close_price, date, "CLOSE_BREACH")
                self._short_position = None
            else:
                return

        if self._short_position is None and self._leaps_position is not None:
            if self._last_short_open and (date - self._last_short_open).days < 5:
                return
            T = self.short_dte / 365.0
            strike = BlackScholes.find_strike_for_delta(px, T, rfr, sigma, self.short_delta, "call")
            if self._leaps_position and strike <= self._leaps_position.strike:
                strike = self._leaps_position.strike + 5
            premium = BlackScholes.call_price(px, strike, T, rfr, sigma)
            if premium < 0.10:
                return
            num_contracts = abs(self._leaps_position.quantity)
            expiration = date + dt.timedelta(days=self.short_dte)
            portfolio.open_option(
                self.ticker, "call", strike, expiration,
                quantity=-num_contracts, premium_per_share=premium, date=date,
            )
            self._short_position = portfolio.option_positions[-1]
            self._last_short_open = date

    def _close_pmcc(self, date, px, sigma, rfr, portfolio):
        if self._short_position is not None and self._short_position in portfolio.option_positions:
            dte = self._short_position.days_to_expiry(date)
            T = max(dte, 1) / 365.0
            close_price = BlackScholes.call_price(px, self._short_position.strike, T, rfr, sigma)
            portfolio.close_option(self._short_position, close_price, date, "EXIT_ATTACK")
            self._short_position = None

        if self._leaps_position is not None and self._leaps_position in portfolio.option_positions:
            dte = self._leaps_position.days_to_expiry(date)
            T = max(dte, 1) / 365.0
            close_price = BlackScholes.call_price(px, self._leaps_position.strike, T, rfr, sigma)
            portfolio.close_option(self._leaps_position, close_price, date, "EXIT_ATTACK")
            self._leaps_position = None

    # ─────────────────────────────────────────────────────────
    # State 1: Defense
    # ─────────────────────────────────────────────────────────

    def _run_defense(self, date, px, portfolio):
        if self.ticker in portfolio.stock_positions:
            return
        shares = int(portfolio.cash * 0.98 // px)
        if shares > 0:
            portfolio.buy_stock(self.ticker, shares, px, date)

    # ─────────────────────────────────────────────────────────
    # State 2: Escape (GLD + Cash + Dip-buy)
    # ─────────────────────────────────────────────────────────

    def _run_escape(self, date, prices, portfolio):
        gld_px = prices.get("GLD")
        qqq_px = prices.get("QQQ")

        if len(self._qqq_history) >= self.dd_window:
            recent = self._qqq_history[-self.dd_window:]
            roll_max = max(recent)
            dd = (self._qqq_history[-1] - roll_max) / roll_max if roll_max > 0 else 0
        else:
            dd = 0

        gld_pct = 0.20
        if dd < -0.30:
            dip_pct = 0.80
        elif dd < -0.20:
            dip_pct = 0.50
        elif dd < -0.10:
            dip_pct = 0.20
        else:
            dip_pct = 0.0

        total_nav = portfolio.cash
        if "GLD" in portfolio.stock_positions and gld_px:
            total_nav += portfolio.stock_positions["GLD"].shares * gld_px
        if self.ticker in portfolio.stock_positions and qqq_px:
            total_nav += portfolio.stock_positions[self.ticker].shares * qqq_px

        if gld_px and gld_px > 0:
            target_gld_value = total_nav * gld_pct
            current_gld_value = portfolio.stock_positions["GLD"].shares * gld_px if "GLD" in portfolio.stock_positions else 0
            if current_gld_value < target_gld_value * 0.8:
                gld_to_buy = int((target_gld_value - current_gld_value) / gld_px)
                if gld_to_buy > 0 and portfolio.cash >= gld_to_buy * gld_px:
                    portfolio.buy_stock("GLD", gld_to_buy, gld_px, date)

        if dip_pct > 0 and qqq_px and qqq_px > 0:
            target_qqq_value = total_nav * dip_pct
            current_qqq_value = portfolio.stock_positions[self.ticker].shares * qqq_px if self.ticker in portfolio.stock_positions else 0
            if current_qqq_value < target_qqq_value * 0.8:
                to_buy = int((target_qqq_value - current_qqq_value) / qqq_px)
                if to_buy > 0 and portfolio.cash >= to_buy * qqq_px:
                    portfolio.buy_stock(self.ticker, to_buy, qqq_px, date)
