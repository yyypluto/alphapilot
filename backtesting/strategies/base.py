"""
Abstract base class for all backtesting strategies.
"""

import datetime as dt
from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    """
    Strategy interface.

    Subclasses implement on_bar() which is called on each trading day.
    """

    def __init__(self, ticker: str, name: str = "Strategy"):
        self.ticker = ticker
        self.name = name

    @abstractmethod
    def on_bar(
        self,
        date: dt.date,
        bar_data: dict,
        portfolio: Any,
        engine: Any,
    ) -> None:
        """
        Called on each trading day.

        Args:
            date: current date
            bar_data: dict with keys: prices, vix, rfr, sigma, sigma_map, date
            portfolio: Portfolio instance
            engine: BacktestEngine instance
        """
        ...
