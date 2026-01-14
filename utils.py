import time
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from config import REQUEST_TIMEOUT, YAHOO_USER_AGENT


def _get_yahoo_session() -> requests.Session:
    """Create a session with Yahoo-friendly headers."""
    session = requests.Session()
    session.headers.update({"User-Agent": YAHOO_USER_AGENT})
    return session


def _get_yahoo_crumb(session: requests.Session) -> Optional[str]:
    """Fetch Yahoo crumb lazily; it can fail on some networks."""
    try:
        resp = session.get(
            "https://query1.finance.yahoo.com/v1/test/getcrumb",
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        return None
    return None


def _fetch_from_yahoo_chart_api(
    ticker: str, period: str = "2y", session: Optional[requests.Session] = None, crumb: Optional[str] = None
) -> Optional[pd.DataFrame]:
    session = session or _get_yahoo_session()
    period_map = {"1y": "1y", "2y": "2y", "5y": "5y"}
    range_val = period_map.get(period, "2y")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "range": range_val,
        "interval": "1d",
        "includePrePost": "false",
    }
    if crumb:
        params["crumb"] = crumb

    try:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429 and crumb is None:
            crumb = _get_yahoo_crumb(session)
            if crumb:
                params["crumb"] = crumb
                response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)

        if response.status_code == 200:
            data = response.json()
            result = data["chart"]["result"][0]

            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]

            df = pd.DataFrame(
                {
                    "Open": quote["open"],
                    "High": quote["high"],
                    "Low": quote["low"],
                    "Close": quote["close"],
                    "Volume": quote["volume"],
                },
                index=pd.to_datetime(timestamps, unit="s"),
            )

            df.index.name = "Date"
            return df.dropna(subset=["Close"])
    except Exception:
        return None
    return None


def _fetch_from_yfinance(ticker: str, period: str = "2y") -> Optional[pd.DataFrame]:
    """Fallback to yfinance which handles cookies/crumb internally."""
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        df.index.name = "Date"
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        return df
    except Exception:
        return None


def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["SMA_200"] = df["Close"].rolling(window=200).mean()
    df["SMA_20"] = df["Close"].rolling(window=20).mean()

    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    exp12 = df["Close"].ewm(span=12, adjust=False).mean()
    exp26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp12 - exp26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    df["BB_Middle"] = df["Close"].rolling(window=20).mean()
    df["BB_Std"] = df["Close"].rolling(window=20).std()
    df["BB_Upper"] = df["BB_Middle"] + (2 * df["BB_Std"])
    df["BB_Lower"] = df["BB_Middle"] - (2 * df["BB_Std"])

    df["Dist_MA200_Pct"] = ((df["Close"] - df["SMA_200"]) / df["SMA_200"])
    return df


@st.cache_data(ttl=3600)
def get_stock_data(tickers: List[str], period: str = "2y") -> Dict[str, pd.DataFrame]:
    """
    Fetch historical data for a list of tickers.
    Tries Yahoo Chart API with crumb, then falls back to yfinance.
    """
    data: Dict[str, pd.DataFrame] = {}
    session = _get_yahoo_session()
    crumb: Optional[str] = None

    for ticker in tickers:
        try:
            df = _fetch_from_yahoo_chart_api(ticker, period, session=session, crumb=crumb)
            if df is None and crumb is None:
                crumb = _get_yahoo_crumb(session)
                if crumb:
                    df = _fetch_from_yahoo_chart_api(ticker, period, session=session, crumb=crumb)

            if df is None or df.empty:
                df = _fetch_from_yfinance(ticker, period)

            if df is not None and not df.empty:
                df = _compute_indicators(df)
                data[ticker] = df
            else:
                st.warning(f"{ticker} 数据获取失败（API 被限流或网络问题），请稍后重试或刷新")
        except Exception as e:
            st.warning(f"获取 {ticker} 数据时出错: {e}")

        time.sleep(0.3)  # Avoid rate limiting

    return data


@st.cache_data(ttl=3600)
def get_fear_and_greed() -> Tuple[Optional[float], str]:
    """
    Fetches CNN Fear & Greed Index with fallback.
    """
    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        "https://production.dataviz.cnn.io/index/fearandgreed/current",
    ]
    headers = {
        "User-Agent": YAHOO_USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/markets/fear-and-greed",
    }

    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                if "fear_and_greed" in data:
                    fng_value = data["fear_and_greed"]["score"]
                    fng_rating = data["fear_and_greed"]["rating"]
                    return float(fng_value), fng_rating
                if "score" in data:
                    return float(data["score"]), data.get("rating", "Unknown")
        except Exception:
            continue

    try:
        alt_url = "https://api.alternative.me/fng/?limit=1"
        r = requests.get(alt_url, headers={"User-Agent": YAHOO_USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            if "data" in data and len(data["data"]) > 0:
                fng_value = int(data["data"][0]["value"])
                fng_rating = data["data"][0]["value_classification"]
                return fng_value, fng_rating
    except Exception:
        pass

    return None, "数据获取失败"


def analyze_smh_qqq_rs(stock_data: Dict[str, pd.DataFrame]) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Compute SMH/QQQ relative strength and detect hardware-vs-index divergence.
    Returns (rs_df, signal_str) where rs_df has RS and normalized RS.
    """
    smh_df = stock_data.get("SMH")
    qqq_df = stock_data.get("QQQ")
    if smh_df is None or qqq_df is None:
        return None, "数据不足"

    # Align by date intersection to avoid NaN
    common_index = smh_df.index.intersection(qqq_df.index)
    if len(common_index) < 25:
        return None, "数据不足"

    df = pd.DataFrame(index=common_index)
    df["SMH"] = smh_df.loc[common_index, "Close"]
    df["QQQ"] = qqq_df.loc[common_index, "Close"]
    df["RS"] = df["SMH"] / df["QQQ"]
    df["RS_norm"] = df["RS"] / df["RS"].iloc[0]

    # Divergence detection
    window = 20
    if len(df) <= window:
        return df, "数据不足"

    qqq_last = df["QQQ"].iloc[-1]
    smh_last = df["SMH"].iloc[-1]
    qqq_high_20 = df["QQQ"].iloc[-window - 1 : -1].max()
    smh_high_20 = df["SMH"].iloc[-window - 1 : -1].max()

    qqq_new_high = qqq_last > qqq_high_20
    smh_new_high = smh_last > smh_high_20
    rs_turning_down = df["RS"].diff().tail(3).mean() < 0

    signal = "⚪️ 暂无背离"
    if qqq_new_high and (not smh_new_high) and rs_turning_down:
        signal = "🔴 预警：硬件动能衰竭（顶背离风险）"

    return df, signal


def calculate_divergence_metrics(
    df_qqq: pd.DataFrame,
    df_soxx: pd.DataFrame,
    window: int = 60,
) -> pd.DataFrame:
    """Calculate QQQ vs SOXX drawdown-based divergence metrics.

    Contract:
    - Inputs: two DataFrames with a Date-like index and a "Close" column.
    - Output: a DataFrame aligned on the common index with:
        QQQ_Close, SOXX_Close,
        QQQ_RollingMax, SOXX_RollingMax,
        QQQ_DD, SOXX_DD,
        Divergence_Signal

    Rules:
    - Rolling Max: past `window` rows (trading days) max of Close.
    - Drawdown (DD): (Price - RollingMax) / RollingMax.
    - Signal:
        * QQQ_DD > -0.02 and SOXX_DD < -0.07 => "🔴 严重背离"
        * QQQ_DD > -0.02 and SOXX_DD < -0.04 => "🟠 轻微背离"
        * else => "🟢 趋势健康"
    """

    if df_qqq is None or df_soxx is None:
        return pd.DataFrame()
    if df_qqq.empty or df_soxx.empty:
        return pd.DataFrame()
    if "Close" not in df_qqq.columns or "Close" not in df_soxx.columns:
        return pd.DataFrame()
    if window <= 0:
        raise ValueError("window must be a positive integer")

    common_index = df_qqq.index.intersection(df_soxx.index)
    if common_index.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=common_index)
    out["QQQ_Close"] = pd.to_numeric(df_qqq.loc[common_index, "Close"], errors="coerce")
    out["SOXX_Close"] = pd.to_numeric(df_soxx.loc[common_index, "Close"], errors="coerce")
    out = out.dropna(subset=["QQQ_Close", "SOXX_Close"])
    if out.empty:
        return out

    out["QQQ_RollingMax"] = out["QQQ_Close"].rolling(window=window, min_periods=1).max()
    out["SOXX_RollingMax"] = out["SOXX_Close"].rolling(window=window, min_periods=1).max()

    # Avoid division by zero
    out["QQQ_DD"] = (out["QQQ_Close"] - out["QQQ_RollingMax"]) / out["QQQ_RollingMax"].replace(0, pd.NA)
    out["SOXX_DD"] = (out["SOXX_Close"] - out["SOXX_RollingMax"]) / out["SOXX_RollingMax"].replace(0, pd.NA)

    severe = (out["QQQ_DD"] > -0.02) & (out["SOXX_DD"] < -0.07)
    mild = (out["QQQ_DD"] > -0.02) & (out["SOXX_DD"] < -0.04)

    out["Divergence_Signal"] = "🟢 趋势健康"
    out.loc[mild, "Divergence_Signal"] = "🟠 轻微背离"
    out.loc[severe, "Divergence_Signal"] = "🔴 严重背离"

    return out
