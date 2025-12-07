import datetime as dt

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

# -----------------------------------------------------------------------------
# 1. Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(**PAGE_CONFIG)

# Custom CSS for styling
st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
    }
    .stDataFrame {
        font-size: 1.1rem;
    }
    /* Improve tooltip visibility */
    .stTooltip {
        background-color: #262730 !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

def analyze_signal(row):
    """The AlphaPilot Brain: Generates trading signals based on technicals."""
    rsi = row.get("RSI")
    dist_ma200 = row.get("Dist_MA200_Pct")
    if rsi is None or dist_ma200 is None:
        return "数据不足"
    if dist_ma200 < 0 and rsi < 35:
        return "🟢 极佳买点 (加倍)"
    if rsi < 30:
        return "🟢 超卖反弹 (买入)"
    if rsi > 75:
        return "🔴 严重超买 (警惕)"
    if dist_ma200 > 0.20:
        return "🟠 估值过高 (持有)"
    return "⚪️ 正常定投"


def _daterange_start(time_range: str) -> dt.date:
    today = dt.date.today()
    if time_range == "1y":
        return today - dt.timedelta(days=365)
    if time_range == "5y":
        return today - dt.timedelta(days=365 * 5)
    return today - dt.timedelta(days=365 * 2)


def load_market_data(time_range: str):
    """
    优先读取 Supabase 中的收盘价/指标；若数据缺失或过旧则退回 API。
    返回: (stock_data_dict, pivot_close_df, source)
    """
    start_date = _daterange_start(time_range)
    tickers_needed = sorted(set(TARGET_ETFS + MACRO_TICKERS + L1_TICKERS))

    market_df = fetch_market_daily(tickers_needed, start=start_date.isoformat())
    stock_data = {}
    pivot_close = None
    source = "db"

    if not market_df.empty:
        market_df["date"] = pd.to_datetime(market_df["date"])
        pivot_close = market_df.pivot(index="date", columns="ticker", values="close").sort_index()
        for t in market_df["ticker"].unique():
            sub = market_df[market_df["ticker"] == t].sort_values("date")
            df = pd.DataFrame(index=sub["date"])
            df["Close"] = pd.to_numeric(sub["close"], errors="coerce")
            if "rsi_14" in sub:
                df["RSI"] = pd.to_numeric(sub["rsi_14"], errors="coerce")
            if "ma200_dist_pct" in sub:
                df["Dist_MA200_Pct"] = pd.to_numeric(sub["ma200_dist_pct"], errors="coerce")
            stock_data[t] = df.dropna(subset=["Close"])

    latest_db = pivot_close.index.max().date() if pivot_close is not None else None
    today = dt.date.today()
    if pivot_close is None or latest_db is None or (today - latest_db).days > 2:
        # 数据缺失或不新鲜，退回 API
        source = "api"
        stock_data = get_stock_data(tickers_needed, period=time_range)
        pivot_close = None

    return stock_data, pivot_close, source


def build_pivot_from_stock(stock_data: dict, tickers: list) -> pd.DataFrame | None:
    frames = {}
    for t in tickers:
        df = stock_data.get(t)
        if df is not None and "Close" in df:
            frames[t] = df["Close"]
    if not frames:
        return None
    pivot = pd.concat(frames, axis=1)
    pivot.columns = frames.keys()
    return pivot


def load_macro():
    macro_df = fetch_macro()
    if macro_df.empty:
        return None
    macro_df["date"] = pd.to_datetime(macro_df["date"])
    return macro_df.sort_values("date")

# -----------------------------------------------------------------------------
# 3. Main Application Logic
# -----------------------------------------------------------------------------

def main():
    st.title("🚀 AlphaPilot - 工程师的个人美股投资驾驶舱")
    st.markdown("Automated Wealth Management Dashboard | **Keep Calm & DCA On**")
    
    # --- Sidebar ---
    st.sidebar.header("⚙️ 驾驶舱设置")
    target_etfs = TARGET_ETFS
    macro_tickers = MACRO_TICKERS
    
    selected_etf = st.sidebar.selectbox("选择详情分析标的", target_etfs)
    time_range = st.sidebar.radio("时间范围", TIME_RANGES, index=1)
    
    # Refresh Data Button
    if st.sidebar.button("刷新数据"):
        st.cache_data.clear()
    
    # Load Data
    with st.spinner("正在读取数据库数据..."):
        stock_data, pivot_close, source = load_market_data(time_range)
        macro_df = load_macro()
        rs_df, rs_signal = analyze_smh_qqq_rs(stock_data)

    if not stock_data:
        st.error("无法获取数据（数据库缺失且 API 失败）。")
        return

    # --- Module A: Macro Dashboard (宏观天眼) ---
    st.subheader("📡 模块 A: 宏观天眼 (Macro Environment)")
    col1, col2, col3 = st.columns(3)
    
    # 1. Fear & Greed
    with col1:
        fng_score, fng_label = (None, None)
        if macro_df is not None and not macro_df.empty and macro_df["fear_greed_index"].notna().any():
            latest_macro = macro_df.iloc[-1]
            fng_score = latest_macro["fear_greed_index"]
            fng_label = "数据库"
        if fng_score is None:
            fng_score, fng_label = get_fear_and_greed()

        if fng_score is not None:
            if fng_score < 25:
                status = "极度恐惧 (买入良机!)"
            elif fng_score > 75:
                status = "极度贪婪 (风险!)"
            else:
                status = f"{fng_label}"
            st.metric("CNN 恐慌贪婪指数", f"{fng_score:.0f}", status)
            if fng_score < 25:
                st.success("🟢 当前市场极度恐惧，贪婪时刻！")
        else:
            st.metric("CNN 恐慌贪婪指数", "N/A", "获取失败")

    # 2. VIX (Volatility)
    with col2:
        vix_val = None
        if macro_df is not None and not macro_df.empty and macro_df["vix_close"].notna().any():
            vix_val = float(macro_df.iloc[-1]["vix_close"])
            st.metric("VIX 恐慌指数", f"{vix_val:.2f}")
            if vix_val > 30:
                st.warning("🟢 VIX > 30，恐慌过度，可能是底部！")
        elif stock_data.get("^VIX") is not None:
            vix_df = stock_data["^VIX"]
            latest_vix = vix_df.iloc[-1]["Close"]
            prev_vix = vix_df.iloc[-2]["Close"]
            vix_change = latest_vix - prev_vix
            st.metric("VIX 恐慌指数", f"{latest_vix:.2f}", f"{vix_change:.2f}")
            if latest_vix > 30:
                st.warning("🟢 VIX > 30，恐慌过度，可能是底部！")

    # 3. US 10Y Yield
    with col3:
        if macro_df is not None and not macro_df.empty and macro_df["us10y_yield"].notna().any():
            latest_tnx = float(macro_df.iloc[-1]["us10y_yield"])
            st.metric("美债 10年期收益率", f"{latest_tnx:.2f}%")
            if latest_tnx > 4.5:
                st.caption("⚠️ 收益率较高，压制成长股估值")
        elif stock_data.get("^TNX") is not None:
            tnx_df = stock_data["^TNX"]
            latest_tnx = tnx_df.iloc[-1]["Close"]
            prev_tnx = tnx_df.iloc[-2]["Close"]
            tnx_change = latest_tnx - prev_tnx
            st.metric("美债 10年期收益率", f"{latest_tnx:.2f}%", f"{tnx_change:.2f}")
            if latest_tnx > 4.5:
                st.caption("⚠️ 收益率较高，压制成长股估值")

    st.markdown("---")

    # --- Module B: Asset Health Monitor (核心资产体检表) ---
    st.subheader("🏥 模块 B: 核心资产体检表 (Asset Health)")
    
    summary_data = []
    for ticker in target_etfs:
        df = stock_data.get(ticker)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            signal = analyze_signal(latest)
            
            summary_data.append({
                "标的": ticker,
                "现价": f"${latest['Close']:.2f}",
                "RSI (14)": round(latest.get("RSI", float("nan")), 1) if "RSI" in latest else None,
                "年线乖离率": f"{latest.get('Dist_MA200_Pct', float('nan')):.1%}" if "Dist_MA200_Pct" in latest else "N/A",
                "AlphaPilot 信号": signal
            })
    
    summary_df = pd.DataFrame(summary_data)
    
    # Custom Styling for DataFrame
    def highlight_rsi(val):
        color = ''
        if val < 30: color = 'background-color: #d4edda; color: green' # Greenish
        elif val > 70: color = 'background-color: #f8d7da; color: red' # Reddish
        return color

    st.dataframe(
        summary_df.style.map(highlight_rsi, subset=['RSI (14)']),
        width="stretch",
        hide_index=True
    )

    st.markdown("---")

    # --- Module C: SMH/QQQ Relative Strength ---
    st.subheader("🧭 模块 C: SMH/QQQ 相对强弱指标")
    if rs_df is not None:
        st.markdown(
            """
            **计算方法**

            - 相对强度 RS = 收盘价(SMH) / 收盘价(QQQ)
            - 归一化 RS = RS / RS首日，用于直观观察趋势斜率
            - 背离判定：若 QQQ 最近20日创新高，SMH 未创新高，且 RS 近几日均值下拐，则触发预警。
            """,
            unsafe_allow_html=False,
        )
        fig_rs = go.Figure()
        fig_rs.add_trace(go.Scatter(
            x=rs_df.index, y=rs_df["RS_norm"],
            mode="lines", name="RS (归一化)",
            line=dict(color="#00b4d8", width=2)
        ))
        fig_rs.add_hline(y=1.0, line_dash="dash", line_color="gray")
        fig_rs.update_layout(
            title="SMH / QQQ Relative Strength",
            height=320,
            template="plotly_dark",
            showlegend=True,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_rs, config={"responsive": True}, use_container_width=True)
        st.info(rs_signal)
    else:
        st.caption(f"相对强弱数据不足：{rs_signal}")

    st.markdown("---")

    # --- Module D: L1 深度分析 ---
    st.subheader("🧠 模块 D: L1 深度分析")
    if pivot_close is None:
        pivot_close = build_pivot_from_stock(stock_data, L1_TICKERS)
    if pivot_close is not None:
        pivot_close = pivot_close.sort_index()
        # 1) AI 产业链背离监测
        if "QQQ" in pivot_close and "SOXX" in pivot_close:
            qqq_series = pivot_close["QQQ"].dropna()
            ratio_series = (pivot_close["SOXX"] / pivot_close["QQQ"]).dropna()
            fig1 = go.Figure()
            fig1.add_trace(go.Scatter(x=qqq_series.index, y=qqq_series, name="QQQ", yaxis="y1", line=dict(color="#4cc9f0")))
            fig1.add_trace(go.Scatter(
                x=ratio_series.index, y=ratio_series, name="SOXX/QQQ", yaxis="y2",
                fill="tozeroy", line=dict(color="#f72585"), opacity=0.35
            ))
            fig1.update_layout(
                title="AI 基建背离监测",
                yaxis=dict(title="QQQ"),
                yaxis2=dict(title="SOXX/QQQ", overlaying="y", side="right"),
                template="plotly_dark",
                height=380,
                legend=dict(orientation="h", y=1.05)
            )
            if len(qqq_series) > 20 and len(ratio_series) > 20:
                if qqq_series.iloc[-1] > qqq_series.iloc[-20:].max() and ratio_series.iloc[-1] < ratio_series.iloc[-20:].max():
                    fig1.add_annotation(text="⚠️ 硬件动能衰竭", x=ratio_series.index[-1], y=ratio_series.iloc[-1],
                                        showarrow=True, arrowcolor="orange", font=dict(color="orange"))
            st.plotly_chart(fig1, use_container_width=True)

        # 2) 聪明钱避险雷达
        if "XLP" in pivot_close and "XLY" in pivot_close:
            xlp_xly = (pivot_close["XLP"] / pivot_close["XLY"]).dropna()
            ma20 = xlp_xly.rolling(20).mean()
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=ma20.index, y=ma20, name="XLP/XLY 20MA", line=dict(color="#ffb703")))
            fig2.update_layout(title="Smart Money Risk-Off", template="plotly_dark", height=320)
            st.plotly_chart(fig2, use_container_width=True)
            if len(ma20.dropna()) > 5 and ma20.iloc[-1] > ma20.iloc[-5:].min() * 1.05:
                st.info("⚠️ XLP/XLY 快速抬升，防御情绪升温")

        # 3) 相关性热力图
        corr_cols = [c for c in ["VOO", "QQQ", "TLT", "SMH"] if c in pivot_close]
        close_for_corr = pivot_close[corr_cols].dropna()
        if not close_for_corr.empty and len(close_for_corr) >= 30:
            recent = close_for_corr.tail(90)
            corr_mat = recent.corr()
            fig3 = px.imshow(
                corr_mat,
                text_auto=".2f",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
                title="近90日资产相关性",
            )
            fig3.update_layout(template="plotly_dark", height=420)
            st.plotly_chart(fig3, use_container_width=True)
            if "TLT" in corr_mat and "QQQ" in corr_mat and corr_mat.loc["TLT", "QQQ"] > 0:
                st.warning("TLT 与 QQQ 由负转正，同跌同涨 → 流动性风险")
    else:
        st.caption("L1 分析数据不足：请先运行 daily_runner 填充数据库或刷新 API。")

    st.markdown("---")

    # --- Module E: Detail Analysis (深度分析) ---
    st.subheader(f"🔍 模块 E: {selected_etf} 深度技术分析")
    
    # ETF Info Expander
    if selected_etf in ETF_INFO:
        info = ETF_INFO[selected_etf]
        with st.expander(f"📖 关于 {selected_etf} ({info['name']})", expanded=True):
            st.markdown(f"{info['desc']}")
            st.markdown(f"**📊 与核心资产关系**: {info['relation']}")
            st.markdown(f"**💡 策略建议**: {info['strategy']}")

    etf_df = stock_data.get(selected_etf)
    if etf_df is None or not all(col in etf_df.columns for col in ["Open", "High", "Low", "Close"]):
        api_detail = get_stock_data([selected_etf], period=time_range)
        etf_df = api_detail.get(selected_etf)
    
    if etf_df is not None:
        # Create Subplots: Main (Price) + RSI + MACD + Volume
        fig = make_subplots(
            rows=4, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.03, 
            row_heights=[0.5, 0.15, 0.15, 0.1],
            subplot_titles=("Price Action & MA", "RSI (14)", "MACD", "Volume")
        )

        # 1. Main Chart: Candlestick + MA + BB
        # Candlestick
        fig.add_trace(go.Candlestick(
            x=etf_df.index,
            open=etf_df['Open'], high=etf_df['High'],
            low=etf_df['Low'], close=etf_df['Close'],
            name='Price'
        ), row=1, col=1)
        
        # MAs
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['SMA_20'], 
            mode='lines', name='MA20 (Short)', 
            line=dict(color='orange', width=1.5)
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['SMA_200'], 
            mode='lines', name='MA200 (Long)', 
            line=dict(color='#0000FF', width=2) # Deep Blue
        ), row=1, col=1)

        # Bollinger Bands
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['BB_Upper'],
            mode='lines', name='BB Upper',
            line=dict(color='gray', width=0.5, dash='dot'),
            showlegend=False
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['BB_Lower'],
            mode='lines', name='BB Lower',
            line=dict(color='gray', width=0.5, dash='dot'),
            fill='tonexty', fillcolor='rgba(128,128,128,0.1)',
            showlegend=False
        ), row=1, col=1)

        # 2. RSI Chart
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['RSI'], 
            mode='lines', name='RSI', 
            line=dict(color='#bf5af2')
        ), row=2, col=1)
        # Thresholds
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        
        # 3. MACD Chart
        fig.add_trace(go.Bar(
            x=etf_df.index, y=etf_df['MACD_Hist'],
            name='MACD Hist',
            marker_color=etf_df['MACD_Hist'].apply(lambda x: 'green' if x >= 0 else 'red')
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['MACD'],
            mode='lines', name='MACD',
            line=dict(color='blue', width=1)
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=etf_df.index, y=etf_df['MACD_Signal'],
            mode='lines', name='Signal',
            line=dict(color='orange', width=1)
        ), row=3, col=1)

        # 4. Volume Chart
        colors = ['red' if row['Open'] - row['Close'] >= 0 else 'green' for index, row in etf_df.iterrows()]
        fig.add_trace(go.Bar(
            x=etf_df.index, y=etf_df['Volume'],
            name='Volume',
            marker_color=colors,
            opacity=0.5
        ), row=4, col=1)

        # Layout Updates
        fig.update_layout(
            height=900,
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            showlegend=True,
            legend=dict(orientation="h", y=1.02),
            margin=dict(l=20, r=20, t=30, b=20)
        )
        
        # Fix Rangebreaks (remove weekends)
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])],
            row=1, col=1
        )

        st.plotly_chart(fig, config={"responsive": True}, use_container_width=True)
        
        # Indicator Explanation Expander
        with st.expander("📊 读懂这些指标 (点击展开)"):
            for name, desc in INDICATOR_INFO.items():
                st.markdown(f"**{name}**")
                st.markdown(f"{desc}")
                st.markdown("---")

if __name__ == "__main__":
    main()
