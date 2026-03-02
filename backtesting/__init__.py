"""
AlphaPilot Backtesting Framework
Options & Stock strategy backtesting with synthetic pricing.
"""

from backtesting.engine import BacktestEngine, Portfolio
from backtesting.metrics import compute_metrics
from backtesting.options_pricing import BlackScholes

__all__ = ["BacktestEngine", "Portfolio", "BlackScholes", "compute_metrics"]
