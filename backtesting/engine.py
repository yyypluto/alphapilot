"""
Core backtesting engine.

Provides Portfolio (tracks cash, positions, NAV) and BacktestEngine
(iterates daily bars, calls strategy hooks, handles option expiration).
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backtesting.options_pricing import BlackScholes, OptionType


# ─────────────────────────────────────────────────────────
# Data classes for positions & trades
# ─────────────────────────────────────────────────────────

@dataclass
class OptionPosition:
    """Represents an open option contract."""

    ticker: str  # underlying
    option_type: OptionType
    strike: float
    expiration: dt.date
    quantity: int  # +1 = long, -1 = short (per contract = 100 shares)
    entry_price: float  # per-share premium at entry
    entry_date: dt.date

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    def days_to_expiry(self, current_date: dt.date) -> int:
        return (self.expiration - current_date).days

    def time_to_expiry_years(self, current_date: dt.date) -> float:
        dte = self.days_to_expiry(current_date)
        return max(dte, 0) / 365.0

    def is_expired(self, current_date: dt.date) -> bool:
        return current_date >= self.expiration

    def intrinsic_value(self, underlying_price: float) -> float:
        if self.option_type == "call":
            return max(underlying_price - self.strike, 0.0)
        return max(self.strike - underlying_price, 0.0)

    def is_itm(self, underlying_price: float) -> bool:
        return self.intrinsic_value(underlying_price) > 0

    def market_value(
        self, underlying_price: float, r: float, sigma: float, current_date: dt.date
    ) -> float:
        """Current market value of this position (per-share, signed by quantity)."""
        T = self.time_to_expiry_years(current_date)
        price_per_share = BlackScholes.price(
            underlying_price, self.strike, T, r, sigma, self.option_type
        )
        return price_per_share * self.quantity * 100


@dataclass
class StockPosition:
    """Represents a stock holding."""

    ticker: str
    shares: int
    cost_basis: float  # average cost per share


@dataclass
class Trade:
    """Record of a completed trade."""

    date: dt.date
    ticker: str
    action: str  # 'BUY_CALL', 'SELL_CALL', 'BUY_PUT', 'SELL_PUT', 'BUY_STOCK', 'SELL_STOCK', 'EXPIRE', 'ASSIGN'
    quantity: int
    price: float  # per-share price
    pnl: float = 0.0  # realized P&L for this trade
    details: str = ""


# ─────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────

class Portfolio:
    """
    Tracks cash, stock positions, option positions, and daily NAV.
    All option quantities are in contracts (1 contract = 100 shares).
    """

    def __init__(self, initial_cash: float = 100_000.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.stock_positions: Dict[str, StockPosition] = {}
        self.option_positions: List[OptionPosition] = []
        self.trades: List[Trade] = []
        self.equity_history: List[Tuple[dt.date, float]] = []

    def total_stock_value(self, prices: Dict[str, float]) -> float:
        """Sum of all stock holdings at current market prices."""
        total = 0.0
        for ticker, pos in self.stock_positions.items():
            px = prices.get(ticker, pos.cost_basis)
            total += pos.shares * px
        return total

    def total_option_value(
        self,
        prices: Dict[str, float],
        r: float,
        sigma_map: Dict[str, float],
        current_date: dt.date,
    ) -> float:
        """Sum of all option positions at current market value."""
        total = 0.0
        for opt in self.option_positions:
            px = prices.get(opt.ticker, 0)
            sigma = sigma_map.get(opt.ticker, 0.20)
            total += opt.market_value(px, r, sigma, current_date)
        return total

    def nav(
        self,
        prices: Dict[str, float],
        r: float,
        sigma_map: Dict[str, float],
        current_date: dt.date,
    ) -> float:
        """Net Asset Value = cash + stock value + option value."""
        return (
            self.cash
            + self.total_stock_value(prices)
            + self.total_option_value(prices, r, sigma_map, current_date)
        )

    def record_nav(
        self,
        date: dt.date,
        prices: Dict[str, float],
        r: float,
        sigma_map: Dict[str, float],
    ) -> float:
        """Snapshot current NAV and append to history."""
        current_nav = self.nav(prices, r, sigma_map, date)
        self.equity_history.append((date, current_nav))
        return current_nav

    # ── Option operations ──

    def open_option(
        self,
        ticker: str,
        option_type: OptionType,
        strike: float,
        expiration: dt.date,
        quantity: int,
        premium_per_share: float,
        date: dt.date,
    ) -> None:
        """
        Open an option position.

        quantity > 0 → buying (pay premium)
        quantity < 0 → selling (receive premium)
        """
        total_premium = premium_per_share * abs(quantity) * 100
        if quantity > 0:
            self.cash -= total_premium
            action = f"BUY_{option_type.upper()}"
        else:
            self.cash += total_premium
            action = f"SELL_{option_type.upper()}"

        pos = OptionPosition(
            ticker=ticker,
            option_type=option_type,
            strike=strike,
            expiration=expiration,
            quantity=quantity,
            entry_price=premium_per_share,
            entry_date=date,
        )
        self.option_positions.append(pos)

        self.trades.append(
            Trade(
                date=date,
                ticker=ticker,
                action=action,
                quantity=quantity,
                price=premium_per_share,
                details=f"K={strike:.0f} exp={expiration} Δ={quantity}",
            )
        )

    def close_option(
        self,
        position: OptionPosition,
        close_price_per_share: float,
        date: dt.date,
        reason: str = "CLOSE",
    ) -> float:
        """
        Close an existing option position. Returns realized P&L.
        """
        if position not in self.option_positions:
            return 0.0

        # P&L = (close - entry) * quantity * 100
        # For long: bought at entry, selling at close → (close - entry) * qty * 100
        # For short: sold at entry, buying back at close → (entry - close) * |qty| * 100
        pnl = (close_price_per_share - position.entry_price) * position.quantity * 100

        # Cash adjustment
        if position.is_long:
            self.cash += close_price_per_share * abs(position.quantity) * 100
        else:
            self.cash -= close_price_per_share * abs(position.quantity) * 100

        self.option_positions.remove(position)

        self.trades.append(
            Trade(
                date=date,
                ticker=position.ticker,
                action=reason,
                quantity=-position.quantity,
                price=close_price_per_share,
                pnl=pnl,
                details=f"K={position.strike:.0f}",
            )
        )
        return pnl

    # ── Stock operations ──

    def buy_stock(self, ticker: str, shares: int, price: float, date: dt.date) -> None:
        """Buy shares of stock."""
        cost = shares * price
        self.cash -= cost

        if ticker in self.stock_positions:
            pos = self.stock_positions[ticker]
            total_shares = pos.shares + shares
            pos.cost_basis = (pos.cost_basis * pos.shares + price * shares) / total_shares
            pos.shares = total_shares
        else:
            self.stock_positions[ticker] = StockPosition(ticker, shares, price)

        self.trades.append(
            Trade(date=date, ticker=ticker, action="BUY_STOCK", quantity=shares, price=price)
        )

    def sell_stock(self, ticker: str, shares: int, price: float, date: dt.date) -> float:
        """Sell shares. Returns realized P&L."""
        if ticker not in self.stock_positions:
            return 0.0
        pos = self.stock_positions[ticker]
        shares = min(shares, pos.shares)
        pnl = (price - pos.cost_basis) * shares

        self.cash += shares * price
        pos.shares -= shares

        if pos.shares <= 0:
            del self.stock_positions[ticker]

        self.trades.append(
            Trade(
                date=date, ticker=ticker, action="SELL_STOCK",
                quantity=shares, price=price, pnl=pnl,
            )
        )
        return pnl

    def get_equity_curve(self) -> pd.Series:
        """Return equity curve as a pandas Series."""
        if not self.equity_history:
            return pd.Series(dtype=float)
        dates, values = zip(*self.equity_history)
        return pd.Series(values, index=pd.DatetimeIndex(dates), name="NAV")


# ─────────────────────────────────────────────────────────
# Backtest Engine
# ─────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Drives the simulation: iterates daily bars, handles option expiration,
    calls strategy hooks.
    """

    def __init__(
        self,
        data: pd.DataFrame,
        strategy: Any,
        initial_cash: float = 100_000.0,
        iv_scale: float = 1.0,
    ):
        """
        Args:
            data: DataFrame from data.fetch_backtest_data()
            strategy: object implementing on_bar(date, data_row, portfolio, engine)
            initial_cash: starting capital
            iv_scale: VIX-to-sigma scale factor (e.g. 1.2 for higher-beta underlyings)
        """
        self.data = data
        self.strategy = strategy
        self.portfolio = Portfolio(initial_cash)
        self.iv_scale = iv_scale
        self.bs = BlackScholes

    def get_sigma(self, vix_value: float) -> float:
        """Convert current VIX to sigma parameter."""
        return BlackScholes.vix_to_sigma(vix_value, self.iv_scale)

    def run(self) -> Portfolio:
        """Execute the backtest. Returns the portfolio with full history."""
        tickers = [
            c for c in self.data.columns if c not in ("VIX", "RFR")
        ]

        for i, (date, row) in enumerate(self.data.iterrows()):
            current_date = date.date() if hasattr(date, "date") else date

            # Current prices
            prices = {}
            for t in tickers:
                val = row.get(t)
                if pd.notna(val):
                    prices[t] = float(val)

            vix = float(row.get("VIX", 20.0))
            rfr = float(row.get("RFR", 0.045))
            sigma = self.get_sigma(vix)
            sigma_map = {t: sigma for t in tickers}

            # ── Handle option expirations ──
            expired = [
                opt
                for opt in self.portfolio.option_positions
                if opt.is_expired(current_date)
            ]
            for opt in expired:
                underlying_px = prices.get(opt.ticker, 0)
                self._handle_expiration(opt, underlying_px, current_date)

            # ── Strategy hook ──
            bar_data = {
                "prices": prices,
                "vix": vix,
                "rfr": rfr,
                "sigma": sigma,
                "sigma_map": sigma_map,
                "date": current_date,
                "row_index": i,
                "total_rows": len(self.data),
            }
            self.strategy.on_bar(current_date, bar_data, self.portfolio, self)

            # ── Record NAV ──
            self.portfolio.record_nav(current_date, prices, rfr, sigma_map)

        return self.portfolio

    def _handle_expiration(
        self, opt: OptionPosition, underlying_price: float, date: dt.date
    ) -> None:
        """Handle option at expiration: assign if ITM, expire worthless if OTM."""
        if opt.is_itm(underlying_price):
            # Assignment
            if opt.option_type == "call":
                if opt.is_long:
                    # Long call ITM → exercise: buy 100 shares at strike
                    self.portfolio.cash -= opt.strike * 100 * abs(opt.quantity)
                    self.portfolio.buy_stock(
                        opt.ticker, 100 * abs(opt.quantity), opt.strike, date
                    )
                    # Undo the buy_stock cash deduction (already done above)
                    self.portfolio.cash += opt.strike * 100 * abs(opt.quantity)
                else:
                    # Short call ITM → assigned: must sell 100 shares at strike
                    if opt.ticker in self.portfolio.stock_positions:
                        shares_to_sell = min(
                            100 * abs(opt.quantity),
                            self.portfolio.stock_positions[opt.ticker].shares,
                        )
                        self.portfolio.sell_stock(
                            opt.ticker, shares_to_sell, opt.strike, date
                        )
                    else:
                        # Cash-settle: pay the difference
                        loss = (underlying_price - opt.strike) * 100 * abs(opt.quantity)
                        self.portfolio.cash -= loss
            else:
                # Put
                if opt.is_long:
                    # Long put ITM → exercise: sell 100 shares at strike
                    if opt.ticker in self.portfolio.stock_positions:
                        self.portfolio.sell_stock(
                            opt.ticker, 100 * abs(opt.quantity), opt.strike, date
                        )
                    else:
                        gain = (opt.strike - underlying_price) * 100 * abs(opt.quantity)
                        self.portfolio.cash += gain
                else:
                    # Short put ITM → assigned: must buy 100 shares at strike
                    self.portfolio.buy_stock(
                        opt.ticker, 100 * abs(opt.quantity), opt.strike, date
                    )

            self.trades_append_assignment(opt, underlying_price, date)
        else:
            # Expire worthless
            self.trades_append_expire(opt, date)

        # Remove from positions
        if opt in self.portfolio.option_positions:
            self.portfolio.option_positions.remove(opt)

    def trades_append_assignment(
        self, opt: OptionPosition, underlying_price: float, date: dt.date
    ) -> None:
        intrinsic = opt.intrinsic_value(underlying_price)
        pnl = (intrinsic - opt.entry_price) * opt.quantity * 100
        self.portfolio.trades.append(
            Trade(
                date=date,
                ticker=opt.ticker,
                action="ASSIGN",
                quantity=opt.quantity,
                price=intrinsic,
                pnl=pnl,
                details=f"K={opt.strike:.0f} {opt.option_type} ITM @ {underlying_price:.2f}",
            )
        )

    def trades_append_expire(self, opt: OptionPosition, date: dt.date) -> None:
        # Profitable for sellers, loss for buyers
        pnl = opt.entry_price * (-opt.quantity) * 100
        self.portfolio.trades.append(
            Trade(
                date=date,
                ticker=opt.ticker,
                action="EXPIRE",
                quantity=opt.quantity,
                price=0.0,
                pnl=pnl,
                details=f"K={opt.strike:.0f} {opt.option_type} OTM → worthless",
            )
        )
