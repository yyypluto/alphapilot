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
    div[data-testid="stMetric"] {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    @media (prefers-color-scheme: dark) {
        div[data-testid="stMetric"] {
            background-color: #262730;
            box-shadow: 0 2px 4px rgba(255,255,255,0.05);
        }
    }
    .stDataFrame { font-size: 1.05rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


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
def main():
    st.title("🚀 AlphaPilot - 工程师的个人美股投资驾驶舱")
    st.caption("Automated Wealth Management Dashboard | **Keep Calm & DCA On**")

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
        for etf_ticker in TARGET_ETFS:
            etf_df = stock_data.get(etf_ticker)
            if etf_df is None or not all(c in etf_df.columns for c in ["Open","High","Low","Close"]):
                api_detail = get_stock_data([etf_ticker], period=time_range)
                etf_df = api_detail.get(etf_ticker)
            
            # Get ETF info for display
            etf_name = ETF_INFO.get(etf_ticker, {}).get('name', etf_ticker)
            etf_strategy = ETF_INFO.get(etf_ticker, {}).get('strategy', '')
            
            # Create expander for each ETF - VOO and QQQ expanded by default
            is_expanded = etf_ticker in ["VOO", "QQQ"]
            with st.expander(f"📈 {etf_ticker} - {etf_name}", expanded=is_expanded):
                if etf_df is not None and not etf_df.empty:
                    # Show ETF info
                    if etf_ticker in ETF_INFO:
                        info = ETF_INFO[etf_ticker]
                        st.markdown(f"**{info['desc']}**")
                        st.caption(f"🎯 策略: {info['strategy']}")
                        st.divider()
                    
                    # Create the chart
                    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                                        row_heights=[0.5,0.15,0.15,0.1],
                                        subplot_titles=("Price & MAs","RSI","MACD","Volume"))
                    fig.add_trace(go.Candlestick(x=etf_df.index, open=etf_df["Open"], high=etf_df["High"],
                                                 low=etf_df["Low"], close=etf_df["Close"], name="Price"), row=1,col=1)
                    fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["SMA_20"], name="MA20", line=dict(color="orange")), row=1,col=1)
                    fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["SMA_200"], name="MA200", line=dict(color="blue")), row=1,col=1)
                    if "BB_Upper" in etf_df and "BB_Lower" in etf_df:
                        fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["BB_Upper"], showlegend=False, line=dict(color="gray", dash="dot", width=0)), row=1,col=1)
                        fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["BB_Lower"], showlegend=False, line=dict(color="gray", dash="dot", width=0),
                                                 fill="tonexty", fillcolor="rgba(128,128,128,0.1)"), row=1,col=1)
                    fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["RSI"], name="RSI", line=dict(color="#bf5af2")), row=2,col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="red", row=2,col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="green", row=2,col=1)
                    if "MACD_Hist" in etf_df.columns:
                        fig.add_trace(go.Bar(x=etf_df.index, y=etf_df["MACD_Hist"], name="MACD Hist",
                                             marker_color=["green" if v>=0 else "red" for v in etf_df["MACD_Hist"]]), row=3,col=1)
                    if "MACD" in etf_df.columns:
                        fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["MACD"], name="MACD", line=dict(color="blue")), row=3,col=1)
                    if "MACD_Signal" in etf_df.columns:
                        fig.add_trace(go.Scatter(x=etf_df.index, y=etf_df["MACD_Signal"], name="Signal", line=dict(color="orange")), row=3,col=1)
                    if "Volume" in etf_df.columns:
                        colors = ["red" if r.Open - r.Close >=0 else "green" for _, r in etf_df.iterrows()]
                        fig.add_trace(go.Bar(x=etf_df.index, y=etf_df["Volume"], name="Volume", marker_color=colors), row=4,col=1)
                    fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.02),
                                      margin=dict(l=10,r=10,t=30,b=10))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning(f"⚠️ {etf_ticker} 数据不可用")
        
        # Indicator explanation at the bottom
        with st.expander("📚 指标解读"):
            for k,v in INDICATOR_INFO.items():
                st.markdown(f"**{k}**: {v}")

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
                fig1.add_trace(go.Scatter(x=qqq_series.index, y=qqq_series, name="QQQ", line=dict(color="#4cc9f0")), secondary_y=False)
                fig1.add_trace(go.Scatter(x=ratio_series.index, y=ratio_series, name="SOXX/QQQ", fill="tozeroy",
                                          line=dict(color="#f72585"), opacity=0.25), secondary_y=True)
                fig1.update_layout(template="plotly_dark", height=360, title="QQQ & SOXX/QQQ")
                st.plotly_chart(fig1, use_container_width=True)
                if len(qqq_series)>20 and len(ratio_series)>20 and qqq_series.iloc[-1]>qqq_series.iloc[-20:].max() and ratio_series.iloc[-1]<ratio_series.iloc[-20:].max():
                    st.warning("⚠️ 硬件动能衰竭：QQQ 创新高但 SOXX/QQQ 走低")

            # 聪明钱避险雷达
            if "XLP" in pivot_close and "XLY" in pivot_close:
                st.subheader("聪明钱避险雷达 (XLP/XLY)")
                xlp_xly = (pivot_close["XLP"]/pivot_close["XLY"]).dropna()
                ma20 = xlp_xly.rolling(20).mean()
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=ma20.index, y=ma20, name="XLP/XLY 20MA", line=dict(color="#ffb703")))
                fig2.update_layout(template="plotly_dark", height=300, title="Defensive vs Cyclical")
                st.plotly_chart(fig2, use_container_width=True)
                if len(ma20.dropna())>5 and ma20.iloc[-1] > ma20.iloc[-5:].min()*1.05:
                    st.info("⚠️ 防御情绪升温：XLP/XLY 快速抬升")

            # 相关性热力图
            corr_cols = [c for c in ["VOO","QQQ","TLT","SMH"] if c in pivot_close]
            close_for_corr = pivot_close[corr_cols].dropna()
            if not close_for_corr.empty and len(close_for_corr)>=30:
                recent = close_for_corr.tail(90)
                corr_mat = recent.corr()
                fig3 = px.imshow(corr_mat, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, title="近90日资产相关性")
                fig3.update_layout(template="plotly_dark", height=360)
                st.plotly_chart(fig3, use_container_width=True)
                if "TLT" in corr_mat and "QQQ" in corr_mat and corr_mat.loc["TLT","QQQ"]>0:
                    st.warning("TLT 与 QQQ 由负转正 → 流动性风险/股债双杀风险")
        else:
            st.warning("L1 数据不足，无法展示宏观/L1 分析。")

    # 跨境 ETF 溢价监控
    with tab3:
        render_premium_dashboard()


if __name__ == "__main__":
    main()








