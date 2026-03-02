"""
Data fetching layer for the backtesting framework.
Downloads historical prices (underlying + VIX) with CSV caching.
"""

import datetime as dt
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_TICKERS = ["QQQ", "SCHG"]
VIX_TICKER = "^VIX"
RFR_TICKER = "^IRX"  # 13-week T-bill yield

DEFAULT_FALLBACK_RFR = 0.045  # 4.5% annual


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
    df = df.sort_index()
    return df


def fetch_backtest_data(
    tickers: Optional[List[str]] = None,
    years: int = 10,
    cache_name: str = "bt_data",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch historical daily data for backtesting.

    Returns a DataFrame indexed by date with columns:
      - One column per underlying ticker (adjusted close prices)
      - 'VIX' — CBOE VIX index close
      - 'RFR' — annualized risk-free rate (from ^IRX or fallback)

    Args:
        tickers: list of underlying tickers (default: QQQ, SCHG)
        years: how many years of history to fetch
        cache_name: CSV cache file basename
        force_refresh: skip cache and re-download
    """
    if tickers is None:
        tickers = DEFAULT_TICKERS

    end_date = dt.date.today()
    start_date = dt.date(end_date.year - years, end_date.month, min(end_date.day, 28))

    cache_path = CACHE_DIR / f"{cache_name}_{years}y.csv"

    # Try cache first
    if not force_refresh and cache_path.exists():
        try:
            cached = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            cached = _ensure_datetime_index(cached)
            all_cols = list(tickers) + ["VIX", "RFR"]
            if not cached.empty and all(c in cached.columns for c in all_cols):
                # Check if cache is reasonably fresh (within 3 days of today)
                if (pd.Timestamp(end_date) - cached.index.max()).days <= 5:
                    print(f"✅ 使用缓存: {cache_path}")
                    return cached
        except Exception:
            pass

    # Download from yfinance
    all_tickers = list(tickers) + [VIX_TICKER, RFR_TICKER]
    print(f"📥 下载数据: {all_tickers} ({start_date} → {end_date}) ...")

    last_err = None
    for attempt in range(3):
        try:
            raw = yf.download(
                all_tickers,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=False,
                progress=True,
            )
            if raw is not None and not raw.empty:
                break
        except Exception as e:
            last_err = e
            time.sleep(2)
    else:
        # Final attempt failed — try cache regardless of freshness
        if cache_path.exists():
            print(f"⚠️ 下载失败，使用过期缓存: {cache_path}")
            cached = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            return _ensure_datetime_index(cached)
        raise RuntimeError(f"数据下载失败: {last_err}")

    # Extract Adj Close
    if "Adj Close" in raw.columns:
        prices = raw["Adj Close"].copy()
    elif "Close" in raw.columns:
        prices = raw["Close"].copy()
    else:
        raise ValueError("yfinance 返回数据缺少 Adj Close / Close 列")

    # Build output DataFrame
    out = pd.DataFrame(index=prices.index)

    for t in tickers:
        if t in prices.columns:
            out[t] = prices[t]
        else:
            print(f"⚠️ {t} 数据缺失，跳过")

    # VIX
    if VIX_TICKER in prices.columns:
        out["VIX"] = prices[VIX_TICKER]
    elif "^VIX" in prices.columns:
        out["VIX"] = prices["^VIX"]
    else:
        print("⚠️ VIX 数据缺失，使用默认值 20")
        out["VIX"] = 20.0

    # Risk-free rate
    if RFR_TICKER in prices.columns:
        # ^IRX is in percent (e.g., 4.5 = 4.5%), convert to decimal
        out["RFR"] = prices[RFR_TICKER] / 100.0
    elif "^IRX" in prices.columns:
        out["RFR"] = prices["^IRX"] / 100.0
    else:
        out["RFR"] = DEFAULT_FALLBACK_RFR

    out = _ensure_datetime_index(out)
    out = out.ffill().dropna(how="all")

    # Cache
    out.to_csv(cache_path)
    print(f"💾 已缓存: {cache_path}")
    print(f"📊 数据范围: {out.index.min().date()} → {out.index.max().date()} ({len(out)} 交易日)")

    return out
