import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import ETF_INFO, INDICATOR_INFO, MACRO_TICKERS, PAGE_CONFIG, TARGET_ETFS, TIME_RANGES
from utils import get_fear_and_greed, get_stock_data

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

# -----------------------------------------------------------------------------
# 2. Main Application Logic
# -----------------------------------------------------------------------------

def analyze_signal(row):
    """
    The AlphaPilot Brain: Generates trading signals based on technicals.
    """
    rsi = row['RSI']
    dist_ma200 = row['Dist_MA200_Pct']
    
    # Logic defined in PRD
    if dist_ma200 < 0 and rsi < 35:
        return "🟢 极佳买点 (加倍)"
    elif rsi < 30:
        return "🟢 超卖反弹 (买入)"
    elif rsi > 75:
        return "🔴 严重超买 (警惕)"
    elif dist_ma200 > 0.20:
        return "🟠 估值过高 (持有)"
    else:
        return "⚪️ 正常定投"

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
    with st.spinner("正在从卫星（Yahoo Finance）接收数据..."):
        stock_data = get_stock_data(target_etfs + macro_tickers, period=time_range)
        fng_score, fng_label = get_fear_and_greed()

    if not stock_data:
        st.error("无法获取股票数据，请检查网络连接。")
        return

    # --- Module A: Macro Dashboard (宏观天眼) ---
    st.subheader("📡 模块 A: 宏观天眼 (Macro Environment)")
    col1, col2, col3 = st.columns(3)
    
    # 1. Fear & Greed
    with col1:
        if fng_score is not None:
            delta_color = "normal"
            if fng_score < 25: 
                status = "极度恐惧 (买入良机!)"
                color = "green"
            elif fng_score > 75: 
                status = "极度贪婪 (风险!)"
                color = "red"
            else:
                status = f"{fng_label}"
                color = "off"
            
            st.metric("CNN 恐慌贪婪指数", f"{fng_score:.0f}", status)
            if fng_score < 25:
                st.success("🟢 当前市场极度恐惧，贪婪时刻！")
        else:
            st.metric("CNN 恐慌贪婪指数", "N/A", "获取失败")

    # 2. VIX (Volatility)
    with col2:
        vix_df = stock_data.get('^VIX')
        if vix_df is not None:
            latest_vix = vix_df.iloc[-1]['Close']
            prev_vix = vix_df.iloc[-2]['Close']
            vix_change = latest_vix - prev_vix
            st.metric("VIX 恐慌指数", f"{latest_vix:.2f}", f"{vix_change:.2f}")
            if latest_vix > 30:
                st.warning("🟢 VIX > 30，恐慌过度，可能是底部！")

    # 3. US 10Y Yield
    with col3:
        tnx_df = stock_data.get('^TNX')
        if tnx_df is not None:
            latest_tnx = tnx_df.iloc[-1]['Close']
            prev_tnx = tnx_df.iloc[-2]['Close']
            tnx_change = latest_tnx - prev_tnx
            st.metric("美债 10年期收益率", f"{latest_tnx:.2f}%", f"{tnx_change:.2f}")
            if latest_tnx > 4.5: # Threshold example
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
                "RSI (14)": round(latest['RSI'], 1),
                "年线乖离率": f"{latest['Dist_MA200_Pct']:.1%}",
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

    # --- Module C: Detail Analysis (深度分析) ---
    st.subheader(f"🔍 模块 C: {selected_etf} 深度技术分析")
    
    # ETF Info Expander
    if selected_etf in ETF_INFO:
        info = ETF_INFO[selected_etf]
        with st.expander(f"📖 关于 {selected_etf} ({info['name']})", expanded=True):
            st.markdown(f"{info['desc']}")
            st.markdown(f"**📊 与核心资产关系**: {info['relation']}")
            st.markdown(f"**💡 策略建议**: {info['strategy']}")

    etf_df = stock_data.get(selected_etf)
    
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

        st.plotly_chart(fig, use_container_width=True)
        
        # Indicator Explanation Expander
        with st.expander("📊 读懂这些指标 (点击展开)"):
            for name, desc in INDICATOR_INFO.items():
                st.markdown(f"**{name}**")
                st.markdown(f"{desc}")
                st.markdown("---")

if __name__ == "__main__":
    main()
