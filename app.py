import datetime as dt
import json
from pathlib import Path
from typing import Optional, Dict, List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config import (
    ETF_INFO,
    INDICATOR_INFO,
    L1_TICKERS,
    MACRO_TICKERS,
    PAGE_CONFIG,
    TARGET_ETFS,
    TIME_RANGES,
)
from db_manager import fetch_macro, fetch_market_daily
from utils import analyze_smh_qqq_rs, get_fear_and_greed, get_stock_data
from premium_calculator import render_premium_dashboard

DEBUG_LOG_PATH = "/Users/xiaoye/Projects/investing/.cursor/debug.log"


def _append_debug_log(payload: dict):
    """Append a small NDJSON log for debug mode; never crash the app."""
    try:
        Path(DEBUG_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        payload.setdefault("timestamp", int(dt.datetime.now().timestamp() * 1000))
        def _default(o):
            if hasattr(o, "item"): return o.item()
            if isinstance(o, (dt.date, dt.datetime)): return o.isoformat()
            return str(o)
        
        with open(DEBUG_LOG_PATH, "a") as _f:
            _f.write(json.dumps(payload, default=_default) + "\n")
    except Exception as e:
        # Swallow logging errors to avoid breaking the UI, but surface in terminal
        try:
            print(f"[debug-log-fail] {e}")
        except Exception:
            pass


def _debug_healthcheck(tag: str) -> bool:
    """
    Verify debug log path is writable; emit a log entry and return existence flag.
    Also prints a small caption in the sidebar for visibility.
    """
    _append_debug_log({
        "sessionId": "debug-session",
        "runId": "pre-fix",
        "hypothesisId": "H0",
        "location": f"app.py:healthcheck:{tag}",
        "message": "healthcheck",
        "data": {"cwd": str(Path.cwd())},
    })
    exists = Path(DEBUG_LOG_PATH).exists()
    try:
        st.sidebar.caption(f"🛠 Debug log ready: {exists} @ {DEBUG_LOG_PATH}")
    except Exception:
        pass
    return exists


#region agent log
_append_debug_log({
    "sessionId": "debug-session",
    "runId": "pre-fix",
    "hypothesisId": "H0",
    "location": "app.py:module:init",
    "message": "module loaded",
})
#endregion

# -----------------------------------------------------------------------------
# 1. Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(**PAGE_CONFIG)

st.markdown(
    """
    <style>
    /* ═══════════════════════════════════════════════════════════════════════
       ALPHAPILOT - Soft Editorial Design System
       A refined, paper-like light theme for comfortable reading
    ═══════════════════════════════════════════════════════════════════════ */
    
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=Lato:wght@400;500;700&family=Source+Code+Pro:wght@400;500&display=swap');
    
    /* CSS Variables - Theme: Warm Paper / Editorial */
    :root {
        --bg-paper: #fbfbf8;
        --bg-card: #ffffff;
        --bg-sidebar: #f4f4f0;
        
        --text-primary: #1f2937;    /* Charcoal */
        --text-secondary: #64748b;  /* Slate */
        --text-accent: #8b5cf6;     /* Soft Violet */
        
        --accent-brand: #ea580c;    /* Burnt Orange */
        --accent-gold: #fbbf24;     /* Warm Yellow */
        
        --status-success: #059669;  /* Emerald */
        --status-success-bg: #ecfdf5;
        --status-danger: #e11d48;   /* Rose */
        --status-danger-bg: #fff1f2;
        --status-warning: #d97706;  /* Amber */
        --status-warning-bg: #fffbeb;
        
        --shadow-soft: 0 4px 20px -2px rgba(0, 0, 0, 0.05);
        --shadow-hover: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
        --border-subtle: #e2e8f0;
    }
    
    /* Global Styles */
    .stApp {
        background-color: var(--bg-paper) !important;
        background-image: radial-gradient(circle at 50% 0%, #fff7ed 0%, transparent 70%); /* Warm light top */
        overflow-x: hidden;
    }

    /* Ambient Bokeh Animation */
    .stApp::before {
        content: "";
        position: fixed;
        top: -10%;
        left: -10%;
        width: 50%;
        height: 50%;
        background: radial-gradient(circle, rgba(234, 88, 12, 0.08) 0%, transparent 70%);
        filter: blur(60px);
        border-radius: 50%;
        animation: float 20s infinite ease-in-out;
        z-index: -1;
        pointer-events: none;
    }

    .stApp::after {
        content: "";
        position: fixed;
        bottom: -10%;
        right: -10%;
        width: 60%;
        height: 60%;
        background: radial-gradient(circle, rgba(5, 150, 105, 0.05) 0%, transparent 70%);
        filter: blur(80px);
        border-radius: 50%;
        animation: float 25s infinite ease-in-out reverse;
        z-index: -1;
        pointer-events: none;
    }
    
    /* Paper Grain Texture Overlay */
    /* We use a simple repeating radial gradient pattern to simulate texture efficiently */
    .app-texture {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' opacity='0.03'/%3E%3C/svg%3E");
        pointer-events: none;
        z-index: 9999; /* On top of everything to give texture */
        opacity: 0.6;
    }
    
    @keyframes float {
        0% { transform: translate(0, 0) rotate(0deg); }
        33% { transform: translate(30px, 50px) rotate(10deg); }
        66% { transform: translate(-20px, 20px) rotate(-5deg); }
        100% { transform: translate(0, 0) rotate(0deg); }
    }
    
    .stApp > header {
        background: transparent !important;
    }
    
    /* Hide Streamlit branding */
    #MainMenu, footer, header[data-testid="stHeader"] {
        visibility: hidden;
    }
    
    /* Typography */
    html, body, [class*="css"] {
        font-family: 'Lato', sans-serif !important;
        color: var(--text-primary) !important;
        line-height: 1.6;
    }
    
    h1, h2, h3, .stTitle {
        font-family: 'Playfair Display', serif !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
    }
    
    h1 {
        font-size: 3rem !important;
        margin-bottom: 0.5rem !important;
        color: #111827 !important;
    }
    
    h2 {
        font-size: 1.8rem !important;
        margin-top: 2rem !important;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--border-subtle);
    }
    
    h3 {
        font-size: 1.3rem !important;
        font-weight: 500 !important;
        color: var(--text-secondary) !important;
    }
    
    /* Helper classes */
    .stCaption {
        font-family: 'Playfair Display', serif !important;
        font-style: italic;
        color: var(--text-secondary) !important;
        font-size: 1rem !important;
    }
    
    /* ═══════════════════════════════════════════════════════════════════════
       METRIC CARDS - Clean Editorial Style
    ═══════════════════════════════════════════════════════════════════════ */
    
    div[data-testid="stMetric"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 16px !important;
        padding: 1.5rem !important;
        box-shadow: var(--shadow-soft) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: var(--shadow-hover) !important;
        border-color: #cbd5e1 !important;
    }
    
    div[data-testid="stMetric"] label {
        color: var(--text-secondary) !important;
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-family: 'Playfair Display', serif !important;
        font-size: 2.2rem !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        font-family: 'Lato', sans-serif !important;
        font-weight: 600 !important;
        background: var(--bg-paper);
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.9rem !important;
    }
    
    /* ═══════════════════════════════════════════════════════════════════════
       DATA TABLES - Minimal & Clean (Light Theme Override)
    ═══════════════════════════════════════════════════════════════════════ */
    
    .stDataFrame {
        border-radius: 16px !important;
        overflow: hidden !important;
        box-shadow: var(--shadow-soft);
        border: 1px solid var(--border-subtle);
        background: var(--bg-card);
    }
    
    .stDataFrame [data-testid="stDataFrameContainer"] {
        border: none !important;
    }
    
    /* Force light theme for dataframe */
    .stDataFrame [data-testid="stDataFrameContainer"] > div,
    .stDataFrame iframe,
    .stDataFrame [class*="glide-data-grid"],
    [data-testid="stDataFrame"] > div > div {
        background-color: #ffffff !important;
    }
    
    /* Table header cells */
    .stDataFrame th,
    [data-testid="stDataFrame"] th,
    .dvn-scroller [role="columnheader"],
    .glideDataEditor [role="columnheader"] {
        background-color: #f8fafc !important;
        color: #64748b !important;
        font-family: 'Lato', sans-serif !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        font-size: 0.75rem !important;
        letter-spacing: 0.05em;
        border-bottom: 1px solid #e2e8f0 !important;
    }
    
    /* Table body cells */
    .stDataFrame td,
    [data-testid="stDataFrame"] td,
    .dvn-scroller [role="gridcell"],
    .glideDataEditor [role="gridcell"] {
        background-color: #ffffff !important;
        font-family: 'Source Code Pro', monospace !important;
        color: #1f2937 !important;
        font-size: 0.9rem !important;
        border-bottom: 1px solid #f1f5f9 !important;
    }
    
    /* Row hover effect */
    .dvn-scroller [role="row"]:hover [role="gridcell"],
    .glideDataEditor [role="row"]:hover [role="gridcell"] {
        background-color: #f8fafc !important;
    }
    
    /* Selected cell */
    .dvn-scroller [role="gridcell"][aria-selected="true"],
    .glideDataEditor [role="gridcell"][aria-selected="true"] {
        background-color: #eff6ff !important;
    }
    
    /* ═══════════════════════════════════════════════════════════════════════
       UI ELEMENTS
    ═══════════════════════════════════════════════════════════════════════ */
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: transparent !important;
        gap: 2rem;
        border-bottom: 1px solid var(--border-subtle);
        padding-bottom: 0px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: var(--text-secondary) !important;
        font-family: 'Lato', sans-serif !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        padding: 0.5rem 0 !important;
        border: none !important;
    }
    
    .stTabs [aria-selected="true"] {
        color: var(--accent-brand) !important;
        border-bottom: 2px solid var(--accent-brand) !important;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: var(--text-primary) !important;
        color: white !important;
        border-radius: 30px !important;
        padding: 0.5rem 2rem !important;
        font-weight: 600 !important;
        border: none !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        background-color: var(--accent-brand) !important;
        transform: translateY(-1px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
    
    /* ═══════════════════════════════════════════════════════════════════════
       SIDEBAR & INPUTS (Soft Editorial)
    ═══════════════════════════════════════════════════════════════════════ */
    
    [data-testid="stSidebar"] {
        background-color: #f8fafc !important; /* Cool grey tint for contrast */
        border-right: 1px solid var(--border-subtle) !important;
    }
    
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: var(--text-primary) !important;
        font-family: 'Playfair Display', serif !important;
    }
    
    /* Input Fields */
    .stSelectbox > div > div {
        background-color: #ffffff !important;
        border-radius: 12px !important;
        border: 1px solid var(--border-subtle) !important;
        color: var(--text-primary) !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
    }
    
    .stMultiSelect > div > div {
        background-color: #ffffff !important;
        border-radius: 12px !important;
        border: 1px solid var(--border-subtle) !important;
    }
    
    /* Expanders in Sidebar */
    [data-testid="stSidebar"] .streamlit-expanderHeader {
        background-color: transparent !important;
        border: none !important;
        font-weight: 600 !important;
        color: var(--text-secondary) !important;
    }
    
    [data-testid="stSidebar"] .streamlit-expanderContent {
        background-color: transparent !important;
        border: none !important;
    }
    
    /* Expanders (Global / Main) */
    .stMain .streamlit-expanderHeader {
        background-color: var(--bg-card) !important;
        border-radius: 12px !important;
        border: 1px solid var(--border-subtle) !important;
        box-shadow: var(--shadow-soft);
    }
    
    .stMain .streamlit-expanderContent {
        background-color: var(--bg-card) !important; /* White card for content */
        border: 1px solid var(--border-subtle) !important;
        border-top: none !important;
        border-radius: 0 0 12px 12px !important;
    }

    /* Plotly Container */
    .stPlotlyChart {
        background: var(--bg-card) !important;
        border-radius: 16px !important;
        box-shadow: var(--shadow-soft) !important;
        padding: 1rem;
        border: 1px solid var(--border-subtle);
    }
    
    /* ═══════════════════════════════════════════════════════════════════════
       DIVIDERS
    ═══════════════════════════════════════════════════════════════════════ */
    
    </style>
    """,
    unsafe_allow_html=True,
)

# Inject Custom CSS for Radio Pills Separation (better placed here)
st.markdown(
    """
    <style>
    /* ═══════════════════════════════════════════════════════════════════════
       RADIO BUTTONS AS PILLS (Horizontal) - Re-injected
    ═══════════════════════════════════════════════════════════════════════ */
    
    /* Container */
    div[role="radiogroup"][aria-orientation="horizontal"] {
        background: var(--bg-card);
        padding: 8px;
        border-radius: 100px; /* Pillow shape */
        border: 1px solid var(--border-subtle);
        box-shadow: var(--shadow-soft);
        display: inline-flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 1.5rem;
    }
    
    /* Individual Options */
    div[role="radiogroup"][aria-orientation="horizontal"] label {
        background: transparent !important;
        border-radius: 40px !important;
        padding: 0.5rem 1.5rem !important;
        border: 1px solid transparent !important;
        font-family: 'Lato', sans-serif !important;
        font-weight: 600 !important;
        cursor: pointer;
        transition: all 0.2s ease;
        margin-right: 0px !important;
    }
    
    div[role="radiogroup"][aria-orientation="horizontal"] label:hover {
        background: var(--bg-paper) !important;
        color: var(--accent-brand) !important;
        transform: translateY(-1px);
    }
    
    /* Active State Handling (Streamlit specific) 
       Streamlit adds a background to the checked div. We override to make it look like a pill.
    */
    div[role="radiogroup"][aria-orientation="horizontal"] label[data-baseweb="radio"] > div:first-child {
        display: none !important; /* Hide circle */
    }
    
    /* Target the selected element text wrapper if possible. 
       Streamlit's DOM for radios changes often. 
       We will rely on visual check. 
       Usually the selected label text gets bolded. */
       
    </style>
    """,
    unsafe_allow_html=True
)


# -----------------------------------------------------------------------------
# Styled Components (Frontend Design)
# -----------------------------------------------------------------------------
def render_etf_stats(df: pd.DataFrame):
    if df is None or df.empty:
        return ""
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    # Calculate metrics
    price = last["Close"]
    change = price - prev["Close"]
    pct_change = (change / prev["Close"]) * 100
    rsi = last.get("RSI", 0)
    
    # Determine colors
    if change >= 0:
        change_color = "#059669" # Emerald
        change_bg = "#ecfdf5"    # Emerald-50
        sign = "+"
        arrow = "▲"
    else:
        change_color = "#e11d48" # Rose
        change_bg = "#fff1f2"    # Rose-50
        sign = ""
        arrow = "▼"
    
    # RSI Status
    rsi_status = "Neutral"
    rsi_color = "#64748b"
    if rsi > 70: 
        rsi_status = "Overbought"
        rsi_color = "#e11d48"
    elif rsi < 30: 
        rsi_status = "Oversold"
        rsi_color = "#059669"
    
    # Build HTML with single-line styles to avoid rendering issues
    container_style = "display:flex;gap:1.5rem;align-items:center;margin-bottom:0.5rem;background:#ffffff;padding:1rem 1.5rem;border-radius:16px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);border:1px solid #f1f5f9;"
    label_style = "font-size:0.8rem;color:#64748b;font-weight:600;text-transform:uppercase;"
    price_style = "font-family:'Source Code Pro',monospace;font-size:1.5rem;font-weight:600;color:#1f2937;"
    divider_style = "border-left:1px solid #e2e8f0;height:40px;"
    change_style = f"font-family:'Source Code Pro',monospace;font-size:1.1rem;font-weight:600;background-color:{change_bg};color:{change_color};padding:4px 12px;border-radius:8px;display:inline-block;margin-top:2px;"
    rsi_container_style = "display:flex;align-items:center;gap:8px;margin-top:2px;"
    rsi_value_style = "font-family:'Source Code Pro',monospace;font-size:1.1rem;font-weight:600;color:#1f2937;"
    rsi_badge_style = f"font-size:0.75rem;background:{rsi_color}15;color:{rsi_color};padding:2px 8px;border-radius:12px;font-weight:600;"
    
    return f'<div style="{container_style}"><div><div style="{label_style}">Latest Price</div><div style="{price_style}">${price:.2f}</div></div><div style="{divider_style}"></div><div><div style="{label_style}">Daily Change</div><div style="{change_style}">{arrow} {sign}{change:.2f} ({sign}{pct_change:.2f}%)</div></div><div style="{divider_style}"></div><div><div style="{label_style}">RSI (14)</div><div style="{rsi_container_style}"><span style="{rsi_value_style}">{rsi:.1f}</span><span style="{rsi_badge_style}">{rsi_status}</span></div></div></div>'

def render_insight_card(title, content, type="warning"):
    colors = {
        "warning": {"bg": "#fffbeb", "border": "#f59e0b", "icon": "⚡️"},
        "info": {"bg": "#eff6ff", "border": "#3b82f6", "icon": "💡"},
        "danger": {"bg": "#fef2f2", "border": "#ef4444", "icon": "🚨"},
    }
    style = colors.get(type, colors["warning"])
    
    st.markdown(f"""
    <div style="
        background: {style['bg']}; 
        border-left: 4px solid {style['border']}; 
        padding: 1.5rem; 
        border-radius: 0 12px 12px 0; 
        margin: 1rem 0;
        font-family: 'Lato', sans-serif;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 0.5rem;">
            <span style="font-size: 1.2rem;">{style['icon']}</span>
            <span style="font-weight: 700; color: #1f2937; font-size: 1.1rem; font-family: 'Playfair Display', serif;">{title}</span>
        </div>
        <div style="color: #4b5563; font-size: 1rem; line-height: 1.6;">
            {content}
        </div>
    </div>
    """, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def analyze_signal(row):
    rsi = row.get("RSI")
    dist = row.get("Dist_MA200_Pct")
    if rsi is None or dist is None:
        return "数据不足"
    if dist < 0 and rsi < 35:
        return "🟢 极佳买点 (加倍)"
    if rsi < 30:
        return "🟢 超卖反弹 (买入)"
    if rsi > 75:
        return "🔴 严重超买 (警惕)"
    if dist > 0.20:
        return "🟠 估值过高 (持有)"
    return "⚪️ 正常定投"


def ensure_indicators(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty or "Close" not in df:
        return df
    if "SMA_20" not in df:
        df["SMA_20"] = df["Close"].rolling(20).mean()
    if "SMA_200" not in df:
        df["SMA_200"] = df["Close"].rolling(200).mean()
    if "RSI" not in df:
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
    if "Dist_MA200_Pct" not in df:
        df["Dist_MA200_Pct"] = (df["Close"] - df["SMA_200"]) / df["SMA_200"]
    return df


def _daterange_start(time_range: str) -> dt.date:
    today = dt.date.today()
    if time_range == "1y":
        return today - dt.timedelta(days=365)
    if time_range == "5y":
        return today - dt.timedelta(days=365 * 5)
    return today - dt.timedelta(days=365 * 2)


def load_market_data(time_range: str):
    start_date = _daterange_start(time_range)
    tickers = sorted(set(TARGET_ETFS + MACRO_TICKERS + L1_TICKERS))

    stock_data: Dict[str, pd.DataFrame] = {}
    pivot_close = None
    source = "db"

    #region agent log
    _append_debug_log({
        "sessionId": "debug-session",
        "runId": "pre-fix",
        "hypothesisId": "H1",
        "location": "app.py:load_market_data:start",
        "message": "load_market_data start",
        "data": {
            "time_range": time_range,
            "start_date": start_date.isoformat(),
            "ticker_count": len(tickers)
        },
    })
    #endregion

    market_df = fetch_market_daily(tickers, start=start_date.isoformat())
    if market_df is not None and not market_df.empty:
        market_df["date"] = pd.to_datetime(market_df["date"])
        pivot_close = market_df.pivot(index="date", columns="ticker", values="close").sort_index()
        for t in market_df["ticker"].unique():
            sub = market_df[market_df["ticker"] == t].sort_values("date")
            df = pd.DataFrame(index=sub["date"].values)
            df["Close"] = sub["close"].values
            if "rsi_14" in sub.columns:
                df["RSI"] = sub["rsi_14"].values
            if "ma200_dist_pct" in sub.columns:
                df["Dist_MA200_Pct"] = sub["ma200_dist_pct"].values
            before_drop = len(df)
            close_notnull = df["Close"].notna().sum()
            df = ensure_indicators(df.dropna(subset=["Close"]))
            stock_data[t] = df
            #region agent log
            _append_debug_log({
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H1",
                "location": "app.py:load_market_data:per_ticker",
                "message": "per ticker stats after db fetch",
                "data": {
                    "ticker": t,
                    "rows_before_drop": before_drop,
                    "close_notnull": close_notnull,
                    "rows_after_drop": len(df),
                },
            })
            #endregion

    #region agent log
    _append_debug_log({
        "sessionId": "debug-session",
        "runId": "pre-fix",
        "hypothesisId": "H1",
        "location": "app.py:load_market_data:post_db",
        "message": "after db fetch",
        "data": {
            "market_rows": len(market_df) if market_df is not None else 0,
            "pivot_close_rows": 0 if pivot_close is None else pivot_close.shape[0],
            "pivot_close_cols": 0 if pivot_close is None else pivot_close.shape[1],
        },
    })
    #endregion

    latest_db = pivot_close.index.max().date() if pivot_close is not None else None
    today = dt.date.today()
    if pivot_close is None or latest_db is None or (today - latest_db).days > 2:
        source = "api"
        stock_data = get_stock_data(tickers, period=time_range)
        for k, v in list(stock_data.items()):
            stock_data[k] = ensure_indicators(v)
        pivot_close = None

    missing_after_load = [t for t in tickers if t not in stock_data or stock_data[t] is None or stock_data[t].empty]
    #region agent log
    _append_debug_log({
        "sessionId": "debug-session",
        "runId": "pre-fix",
        "hypothesisId": "H2",
        "location": "app.py:load_market_data:end",
        "message": "load_market_data end",
        "data": {
            "source": source,
            "stock_data_keys": list(stock_data.keys()),
            "missing_tickers": missing_after_load,
            "pivot_close_present": pivot_close is not None
        },
    })
    #endregion

    return stock_data, pivot_close, source


def build_pivot_from_stock(stock_data: dict, tickers: List[str]) -> Optional[pd.DataFrame]:
    frames = {}
    for t in tickers:
        df = stock_data.get(t)
        if df is not None and "Close" in df:
            frames[t] = df["Close"]
    if not frames:
        return None
    return pd.concat(frames, axis=1)


def load_macro():
    macro_df = fetch_macro()
    if macro_df is None or macro_df.empty:
        return None
    macro_df["date"] = pd.to_datetime(macro_df["date"])
    return macro_df.sort_values("date")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
# Custom Plotly theme - Soft Editorial
ALPHAPILOT_PLOTLY_TEMPLATE = {
    "layout": {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Lato, sans-serif", "color": "#64748b"},
        "title": {"font": {"family": "Playfair Display, serif", "color": "#1f2937", "size": 20}},
        "xaxis": {
            "gridcolor": "#f1f5f9",
            "linecolor": "#e2e8f0",
            "tickfont": {"color": "#64748b"},
        },
        "yaxis": {
            "gridcolor": "#f1f5f9",
            "linecolor": "#e2e8f0",
            "tickfont": {"color": "#64748b"},
        },
        "colorway": ["#ea580c", "#059669", "#3b82f6", "#8b5cf6", "#e11d48", "#f59e0b"],
    }
}


def main():
    # Inject grain texture
    st.markdown('<div class="app-texture"></div>', unsafe_allow_html=True)

    # Premium header - Clean Editorial
    st.markdown(
        '''
        <div style="text-align: center; padding: 2rem 0 1rem 0;">
            <div style="font-family: 'Playfair Display', serif; font-size: 1.2rem; color: #ea580c; font-style: italic;">
                The Engineer's Wealth Journal
            </div>
            <div style="font-size: 3.5rem; color: #1f2937; font-weight: 700; margin-top: -10px;">
                AlphaPilot
            </div>
            <hr style="width: 50px; border-top: 3px solid #ea580c; margin: 1rem auto; opacity: 1;">
        </div>
        ''',
        unsafe_allow_html=True
    )

    # Debug healthcheck ensures log file is created early
    _debug_healthcheck("main_entry")

    # Sidebar
    st.sidebar.header("⚙️ 驾驶舱设置")
    time_range = st.sidebar.radio("时间范围", TIME_RANGES, index=1)
    if st.sidebar.button("🔄 刷新数据"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("正在读取数据..."):
        stock_data, pivot_close, source = load_market_data(time_range)
        macro_df = load_macro()
        rs_df, rs_signal = analyze_smh_qqq_rs(stock_data)

    st.sidebar.caption(f"📊 数据源: {source.upper()}")

    if not stock_data:
        st.error("无法获取数据（数据库缺失且 API 失败）。")
        return

    # Macro Dashboard
    st.subheader("📡 宏观天眼 (Macro Environment)")
    col1, col2, col3 = st.columns(3)

    # 1) CNN Fear & Greed
    with col1:
        fng_score, fng_label = (None, None)
        if macro_df is not None and not macro_df.empty and macro_df["fear_greed_index"].notna().any():
            valid = macro_df[macro_df["fear_greed_index"].notna()]
            if not valid.empty:
                fng_score = valid.iloc[-1]["fear_greed_index"]
                fng_label = "DB"
        if fng_score is None:
            fng_score, fng_label = get_fear_and_greed()
        if fng_score is not None:
            delta_color = "off"
            status = fng_label
            if fng_score < 25:
                status = "极度恐惧 (买!)"; delta_color = "inverse"
            elif fng_score > 75:
                status = "极度贪婪 (警惕!)"; delta_color = "normal"
            st.metric("CNN 恐慌贪婪指数", f"{fng_score:.0f}", status, delta_color=delta_color)
        else:
            st.metric("CNN 恐慌贪婪指数", "待更新", "")

    # 2) VIX
    with col2:
        vix_val = None; vix_series = None
        if macro_df is not None and not macro_df.empty and macro_df["vix_close"].notna().any():
            valid = macro_df[macro_df["vix_close"].notna()]
            if not valid.empty:
                vix_val = float(valid.iloc[-1]["vix_close"])
                vix_series = valid.set_index("date")["vix_close"]
        elif stock_data.get("^VIX") is not None:
            vix_df = stock_data["^VIX"]
            if not vix_df.empty:
                vix_val = vix_df.iloc[-1]["Close"]
                vix_series = vix_df["Close"]
        else:
            api_vix = get_stock_data(["^VIX"], period="6mo")
            if api_vix.get("^VIX") is not None:
                vix_df = api_vix["^VIX"]
                vix_val = vix_df.iloc[-1]["Close"]
                vix_series = vix_df["Close"]

        if vix_val is not None and not pd.isna(vix_val):
            delta_vix = 0
            if vix_series is not None and len(vix_series) > 1:
                delta_vix = vix_val - vix_series.iloc[-2]
            st.metric("VIX 恐慌指数", f"{vix_val:.2f}", f"{delta_vix:.2f}", delta_color="inverse")
            with st.expander("📉 VIX 趋势", expanded=False):
                if vix_series is not None:
                    st.line_chart(vix_series.tail(90), height=150)
        else:
            st.metric("VIX 恐慌指数", "待更新", "")

    # 3) TNX
    with col3:
        tnx_val = None; tnx_series = None
        if macro_df is not None and not macro_df.empty and macro_df["us10y_yield"].notna().any():
            valid = macro_df[macro_df["us10y_yield"].notna()]
            if not valid.empty:
                tnx_val = float(valid.iloc[-1]["us10y_yield"])
                tnx_series = valid.set_index("date")["us10y_yield"]
        elif stock_data.get("^TNX") is not None:
            tnx_df = stock_data["^TNX"]
            if not tnx_df.empty:
                tnx_val = tnx_df.iloc[-1]["Close"]
                tnx_series = tnx_df["Close"]
        else:
            api_tnx = get_stock_data(["^TNX"], period="6mo")
            if api_tnx.get("^TNX") is not None:
                tnx_df = api_tnx["^TNX"]
                tnx_val = tnx_df.iloc[-1]["Close"]
                tnx_series = tnx_df["Close"]

        if tnx_val is not None and not pd.isna(tnx_val):
            delta_tnx = 0
            if tnx_series is not None and len(tnx_series) > 1:
                delta_tnx = tnx_val - tnx_series.iloc[-2]
            st.metric("美债 10年期收益率", f"{tnx_val:.2f}%", f"{delta_tnx:.2f}", delta_color="inverse")
            with st.expander("📈 收益率趋势", expanded=False):
                if tnx_series is not None:
                    st.line_chart(tnx_series.tail(90), height=150)
        else:
            st.metric("美债 10年期收益率", "待更新", "")

    st.divider()

    # Asset Overview
    st.subheader("🏥 核心资产体检表 (Asset Overview)")
    summary_data = []
    for t in TARGET_ETFS:
        df = stock_data.get(t)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            summary_data.append({
                "标的": t,
                "现价": f"${latest['Close']:.2f}",
                "RSI (14)": round(latest.get("RSI", float("nan")), 1) if "RSI" in latest else None,
                "年线乖离率": f"{latest.get('Dist_MA200_Pct', float('nan')):.1%}" if "Dist_MA200_Pct" in latest else "N/A",
                "信号": analyze_signal(latest)
            })
    summary_df = pd.DataFrame(summary_data)

    missing_targets = [t for t in TARGET_ETFS if t not in stock_data or stock_data[t] is None or stock_data[t].empty]
    #region agent log
    _append_debug_log({
        "sessionId": "debug-session",
        "runId": "pre-fix",
        "hypothesisId": "H3",
        "location": "app.py:main:asset_overview",
        "message": "asset overview summary",
        "data": {
            "summary_rows": len(summary_df),
            "missing_targets": missing_targets
        },
    })
    #endregion

    def highlight_rsi(val):
        if pd.isna(val): return ''
        if val < 30: return 'background-color: rgba(0,255,0,0.2); color: green'
        if val > 70: return 'background-color: rgba(255,0,0,0.2); color: red'
        return ''
    styler = summary_df.style
    if "RSI (14)" in summary_df.columns:
        styler = styler.map(highlight_rsi, subset=["RSI (14)"])
    st.dataframe(styler, width="stretch", hide_index=True)


    st.divider()

    # Tabs
    tab1, tab2, tab3 = st.tabs(["🔍 深度技术分析", "🧠 宏观/L1 分析", "🌏 跨境搬砖"])

    with tab1:
        st.subheader("📊 所有标的技术分析")
        st.caption("点击展开查看各标的详细技术图表")
        
        # Display all ETFs in expandable sections
        # Modern Pill Navigation
        st.write("") # Spacer
        
        # 1. Selector Row
        selected_ticker = st.radio(
            "Select Asset", 
            TARGET_ETFS, 
            horizontal=True, 
            label_visibility="collapsed",
            key="etf_selector_main"
        )
        
        # 2. Display Area
        etf_ticker = selected_ticker
        etf_df = stock_data.get(etf_ticker)
        
        # Fallback fetch if needed
        if etf_df is None or not all(c in etf_df.columns for c in ["Open","High","Low","Close"]):
            api_detail = get_stock_data([etf_ticker], period=time_range)
            etf_df = api_detail.get(etf_ticker)
            
        # 3. Content Card with Animation
        if etf_df is not None and not etf_df.empty:
            st.markdown(f"""
            <div style="animation: fadeInUp 0.5s ease-out;">
                <h3 style="margin-top:0; color: #ea580c; display:flex; align-items:center;">
                    📈 {etf_ticker} <span style="font-size:0.8em; color:#64748b; margin-left:10px; font-weight:400;">{ETF_INFO.get(etf_ticker, {}).get('name', '')}</span>
                </h3>
            </div>
            """, unsafe_allow_html=True)
            
            # Info Section
            if etf_ticker in ETF_INFO:
                info = ETF_INFO[etf_ticker]
                st.markdown(f"""
                <div style="background:var(--bg-paper); padding:1rem; border-radius:12px; border:1px solid var(--border-subtle); margin-bottom:1.5rem;">
                    <div style="font-style:italic; margin-bottom:0.5rem;">{info['desc']}</div>
                    <div style="display:flex; gap:10px; font-size:0.9rem;">
                        <span style="background:#ecfdf5; color:#059669; padding:2px 8px; border-radius:6px; font-weight:600;">🎯 {info['strategy']}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Quick Stats Banner
            st.markdown(render_etf_stats(etf_df), unsafe_allow_html=True)

            # Chart
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                                row_heights=[0.5,0.15,0.15,0.1],
                                subplot_titles=("Price & MAs","RSI","MACD","Volume"))
            fig.add_trace(go.Candlestick(x=etf_df.index, open=etf_df["Open"], high=etf_df["High"],
                                            low=etf_df["Low"], close=etf_df["Close"], name="Price"), row=1,col=1)
            fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["SMA_20"], name="MA20", line=dict(color="#f59e0b")), row=1,col=1)
            fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["SMA_200"], name="MA200", line=dict(color="#3b82f6")), row=1,col=1)
            if "BB_Upper" in etf_df and "BB_Lower" in etf_df:
                fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["BB_Upper"], showlegend=False, line=dict(color="#94a3b8", dash="dot", width=0)), row=1,col=1)
                fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["BB_Lower"], showlegend=False, line=dict(color="#94a3b8", dash="dot", width=0),
                                            fill="tonexty", fillcolor="rgba(148, 163, 184, 0.1)"), row=1,col=1)
            fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["RSI"], name="RSI", line=dict(color="#8b5cf6")), row=2,col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#e11d48", row=2,col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#10b981", row=2,col=1)
            if "MACD_Hist" in etf_df.columns:
                fig.add_trace(go.Bar(x=etf_df.index, y=etf_df["MACD_Hist"], name="MACD Hist",
                                        marker_color=["#10b981" if v>=0 else "#e11d48" for v in etf_df["MACD_Hist"]]), row=3,col=1)
            if "MACD" in etf_df.columns:
                fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["MACD"], name="MACD", line=dict(color="#3b82f6")), row=3,col=1)
            if "MACD_Signal" in etf_df.columns:
                fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["MACD_Signal"], name="Signal", line=dict(color="#f59e0b")), row=3,col=1)
            if "Volume" in etf_df.columns:
                colors = ["#e11d48" if r.Open - r.Close >=0 else "#10b981" for _, r in etf_df.iterrows()]
                fig.add_trace(go.Bar(x=etf_df.index, y=etf_df["Volume"], name="Volume", marker_color=colors), row=4,col=1)
            
            # Apply custom theme
            fig.update_layout(
                height=700,
                template="plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Lato, sans-serif", color="#64748b"),
                xaxis_rangeslider_visible=False,
                legend=dict(orientation="h", y=1.02),
                margin=dict(l=10, r=10, t=30, b=10),
            )
            fig.update_xaxes(gridcolor="#f1f5f9", linecolor="#e2e8f0")
            fig.update_yaxes(gridcolor="#f1f5f9", linecolor="#e2e8f0")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"⚠️ {etf_ticker} 数据不可用")
        
        # Indicator explanation at the bottom (Collapsible manual)
        with st.expander("📚 指标解读手册"):
            st.markdown("""
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
            """, unsafe_allow_html=True)
            for k,v in INDICATOR_INFO.items():
                st.markdown(f"<div><strong style='color:#ea580c'>{k}</strong><br><span style='font-size:0.9em; color:#64748b'>{v}</span></div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # Macro / L1
    with tab2:
        if pivot_close is None:
            pivot_close = build_pivot_from_stock(stock_data, L1_TICKERS)
        if pivot_close is not None:
            pivot_close = pivot_close.sort_index()

            # AI 产业链背离
            if "QQQ" in pivot_close and "SOXX" in pivot_close:
                st.subheader("AI 基建背离 (QQQ vs SOXX/QQQ)")
                qqq_series = pivot_close["QQQ"].dropna()
                ratio_series = (pivot_close["SOXX"] / pivot_close["QQQ"]).dropna()
                fig1 = make_subplots(specs=[[{"secondary_y": True}]])
                fig1.add_trace(go.Scatter(x=qqq_series.index, y=qqq_series, name="QQQ", line=dict(color="#3b82f6", width=2)), secondary_y=False)
                fig1.add_trace(go.Scatter(x=ratio_series.index, y=ratio_series, name="SOXX/QQQ", fill="tozeroy",
                                          line=dict(color="#ea580c"), opacity=0.1), secondary_y=True)
                fig1.update_layout(
                    template="plotly_white", 
                    height=360, 
                    title="QQQ & SOXX/QQQ",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Lato, sans-serif", color="#64748b"),
                )
                fig1.update_xaxes(gridcolor="#f1f5f9")
                fig1.update_yaxes(gridcolor="#f1f5f9")
                st.plotly_chart(fig1, use_container_width=True)
                if len(qqq_series)>20 and len(ratio_series)>20 and qqq_series.iloc[-1]>qqq_series.iloc[-20:].max() and ratio_series.iloc[-1]<ratio_series.iloc[-20:].max():
                    render_insight_card(
                        "硬件动能衰竭预警", 
                        "QQQ 创出新高的同时，芯片股相对于 QQQ 的强度 (SOXX/QQQ) 却在走低。这通常意味着市场由少数权重股拉动，由于芯片是本轮 AI 硬件周期的核心，这种背离值得警惕。", 
                        "warning"
                    )

            # 聪明钱避险雷达
            if "XLP" in pivot_close and "XLY" in pivot_close:
                st.subheader("聪明钱避险雷达 (XLP/XLY)")
                xlp_xly = (pivot_close["XLP"]/pivot_close["XLY"]).dropna()
                ma20 = xlp_xly.rolling(20).mean()
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=ma20.index, y=ma20, name="XLP/XLY 20MA", line=dict(color="#f59e0b", width=2)))
                fig2.update_layout(
                    template="plotly_white", 
                    height=300, 
                    title="Defensive vs Cyclical",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Lato, sans-serif", color="#64748b"),
                )
                fig2.update_xaxes(gridcolor="#f1f5f9")
                fig2.update_yaxes(gridcolor="#f1f5f9")
                st.plotly_chart(fig2, use_container_width=True)
                if len(ma20.dropna())>5 and ma20.iloc[-1] > ma20.iloc[-5:].min()*1.05:
                    render_insight_card(
                        "防御情绪快速升温",
                        "必须消费品 (XLP) 相对 可选消费品 (XLY) 的比率在短期内快速抬升。这表明大资金正在从进攻转向防御，通常是市场回调的前兆。",
                        "info"
                    )

            # 相关性热力图
            corr_cols = [c for c in ["VOO","QQQ","TLT","SMH"] if c in pivot_close]
            close_for_corr = pivot_close[corr_cols].dropna()
            if not close_for_corr.empty and len(close_for_corr)>=30:
                recent = close_for_corr.tail(90)
                corr_mat = recent.corr()
                fig3 = px.imshow(corr_mat, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, title="近90日资产相关性")
                fig3.update_layout(
                    template="plotly_white", 
                    height=360,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Lato, sans-serif", color="#64748b"),
                )
                st.plotly_chart(fig3, use_container_width=True)
                if "TLT" in corr_mat and "QQQ" in corr_mat and corr_mat.loc["TLT","QQQ"]>0:
                    render_insight_card(
                        "股债相关性异常警报",
                        "长期以来 TLT (美债) 与 QQQ (纳指) 呈负相关（股债跷跷板）。近期相关性转正，可能意味着流动性风险上升，警惕股债双杀。",
                        "danger"
                    )
        else:
            st.warning("L1 数据不足，无法展示宏观/L1 分析。")

    # 跨境 ETF 溢价监控
    with tab3:
        render_premium_dashboard()


if __name__ == "__main__":
    main()








