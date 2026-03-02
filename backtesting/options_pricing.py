"""
Black-Scholes options pricing engine for synthetic backtesting.

Uses VIX as an implied volatility proxy. Provides:
- Call / Put pricing
- Delta calculation
- Strike finder for a target delta (bisection)
"""

import math
from typing import Literal

import numpy as np
from scipy.stats import norm


OptionType = Literal["call", "put"]


class BlackScholes:
    """Stateless Black-Scholes calculator."""

    @staticmethod
    def d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Compute d1 in the BS formula."""
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0.0
        return (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))

    @staticmethod
    def d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Compute d2 in the BS formula."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return BlackScholes.d1(S, K, T, r, sigma) - sigma * math.sqrt(T)

    @staticmethod
    def call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """
        European call option price.

        Args:
            S: underlying price
            K: strike price
            T: time to expiration in years
            r: risk-free rate (annualized, decimal)
            sigma: volatility (annualized, decimal)
        """
        if T <= 0:
            return max(S - K, 0.0)
        _d1 = BlackScholes.d1(S, K, T, r, sigma)
        _d2 = BlackScholes.d2(S, K, T, r, sigma)
        return S * norm.cdf(_d1) - K * math.exp(-r * T) * norm.cdf(_d2)

    @staticmethod
    def put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """European put option price."""
        if T <= 0:
            return max(K - S, 0.0)
        _d1 = BlackScholes.d1(S, K, T, r, sigma)
        _d2 = BlackScholes.d2(S, K, T, r, sigma)
        return K * math.exp(-r * T) * norm.cdf(-_d2) - S * norm.cdf(-_d1)

    @staticmethod
    def price(
        S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType
    ) -> float:
        """Price a call or put."""
        if option_type == "call":
            return BlackScholes.call_price(S, K, T, r, sigma)
        return BlackScholes.put_price(S, K, T, r, sigma)

    @staticmethod
    def delta(
        S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType
    ) -> float:
        """
        Option delta.

        Returns:
            Call delta ∈ [0, 1], Put delta ∈ [-1, 0]
        """
        if T <= 0:
            if option_type == "call":
                return 1.0 if S > K else 0.0
            return -1.0 if S < K else 0.0
        _d1 = BlackScholes.d1(S, K, T, r, sigma)
        if option_type == "call":
            return norm.cdf(_d1)
        return norm.cdf(_d1) - 1.0

    @staticmethod
    def theta(
        S: float, K: float, T: float, r: float, sigma: float, option_type: OptionType
    ) -> float:
        """Option theta (per calendar day)."""
        if T <= 0:
            return 0.0
        _d1 = BlackScholes.d1(S, K, T, r, sigma)
        _d2 = BlackScholes.d2(S, K, T, r, sigma)
        term1 = -(S * sigma * norm.pdf(_d1)) / (2 * math.sqrt(T))
        if option_type == "call":
            term2 = -r * K * math.exp(-r * T) * norm.cdf(_d2)
        else:
            term2 = r * K * math.exp(-r * T) * norm.cdf(-_d2)
        return (term1 + term2) / 365.0

    @staticmethod
    def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Option gamma (same for call and put)."""
        if T <= 0 or sigma <= 0 or S <= 0:
            return 0.0
        _d1 = BlackScholes.d1(S, K, T, r, sigma)
        return norm.pdf(_d1) / (S * sigma * math.sqrt(T))

    @staticmethod
    def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Option vega (per 1% change in vol)."""
        if T <= 0 or sigma <= 0:
            return 0.0
        _d1 = BlackScholes.d1(S, K, T, r, sigma)
        return S * math.sqrt(T) * norm.pdf(_d1) / 100.0

    @staticmethod
    def find_strike_for_delta(
        S: float,
        T: float,
        r: float,
        sigma: float,
        target_delta: float,
        option_type: OptionType,
        tol: float = 0.001,
        max_iter: int = 100,
    ) -> float:
        """
        Find the strike price that produces the target delta via bisection.

        Args:
            target_delta: for calls, positive (e.g. 0.80); for puts, negative (e.g. -0.15)
            tol: convergence tolerance on delta
        """
        # Search bounds
        low_K = S * 0.30
        high_K = S * 2.00

        for _ in range(max_iter):
            mid_K = (low_K + high_K) / 2.0
            mid_delta = BlackScholes.delta(S, mid_K, T, r, sigma, option_type)

            if abs(mid_delta - target_delta) < tol:
                return round(mid_K, 0)  # Round to nearest dollar

            # Delta is monotonically decreasing in K for calls,
            # and monotonically increasing (less negative) in K for puts
            if option_type == "call":
                if mid_delta > target_delta:
                    low_K = mid_K  # Need higher strike → lower delta
                else:
                    high_K = mid_K
            else:  # put
                if mid_delta < target_delta:
                    high_K = mid_K  # Need lower strike → less negative delta
                else:
                    low_K = mid_K

        return round((low_K + high_K) / 2.0, 0)

    @staticmethod
    def vix_to_sigma(vix: float, scale: float = 1.0) -> float:
        """
        Convert VIX index value to annualized volatility (sigma).

        VIX represents the market's expectation of 30-day S&P 500 volatility,
        annualized. For individual equities, a scale factor can adjust.

        Args:
            vix: VIX index value (e.g. 20.0 means 20%)
            scale: multiplier (e.g. 1.2 for higher-beta assets like QQQ)
        """
        return (vix / 100.0) * scale
