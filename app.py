import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import yfinance as yf
from datetime import datetime, timedelta
import time

# -----------------------------------------------------------------------------
# 1. Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AlphaPilot - 工程师的个人美股投资驾驶舱",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
# 2. Knowledge Base & Config
# -----------------------------------------------------------------------------

ETF_INFO = {
    "VOO": {
        "name": "Vanguard S&P 500 ETF",
        "desc": "🇺🇸 **美国国运基石**。追踪标普 500 指数，包含美国最大的 500 家上市公司。它是你投资组合的压舱石。",
        "relation": "基准指数。所有其他资产都应参考与 VOO 的相关性。",
        "strategy": "核心仓位 (40-50%)"
    },
    "QQQ": {
        "name": "Invesco QQQ Trust",
        "desc": "💻 **科技成长引擎**。追踪纳斯达克 100 指数，重仓 Apple, Microsoft, Nvidia 等科技巨头。",
        "relation": "高贝塔 (High Beta) 资产。通常在牛市中跑赢 VOO，熊市中跌幅更大。",
        "strategy": "进攻仓位 (30-40%)"
    },
    "SMH": {
        "name": "VanEck Semiconductor ETF",
        "desc": "⚡️ **算力时代的石油**。追踪半导体指数，重仓 Nvidia, TSMC, AMD。AI 时代的核心受益者。",
        "relation": "极高波动性。与 QQQ 高度相关，但爆发力更强。",
        "strategy": "卫星仓位 (10-20%)"
    },
    "TLT": {
        "name": "iShares 20+ Year Treasury Bond ETF",
        "desc": "🛡️ **长期国债防守**。追踪美国 20 年期以上国债。通常在经济衰退或股市暴跌时上涨（避险属性）。",
        "relation": "负相关资产。理想情况下与股票走势相反，用于对冲风险。",
        "strategy": "对冲仓位 (0-10%)"
    }
}

# -----------------------------------------------------------------------------
# 3. Data Fetching & Processing
# -----------------------------------------------------------------------------

def _get_yahoo_session():
    """Create a session with Yahoo-friendly headers."""
    session = requests.Session()
    session.headers.update({
        # Simpler UA seems to avoid Yahoo rate-limit edge responses
        "User-Agent": "Mozilla/5.0"
    })
    return session

def _get_yahoo_crumb(session):
    """
    Fetch Yahoo crumb lazily. Some networks return 401 here, so only call it
    when the chart API starts rate limiting.
    """
    try:
        resp = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return None

def _fetch_from_yahoo_chart_api(ticker, period="2y", session=None, crumb=None):
    """Fetch data using Yahoo Finance chart API directly."""
    session = session or requests.Session()
    period_map = {"1y": "1y", "2y": "2y", "5y": "5y"}
    range_val = period_map.get(period, "2y")
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "range": range_val,
        "interval": "1d",
        "includePrePost": "false"
    }
    if crumb:
        params["crumb"] = crumb
    try:
        response = session.get(url, params=params, timeout=15)
        if response.status_code == 429 and crumb is None:
            # Lazily fetch crumb and retry once if we hit rate limit.
            crumb = _get_yahoo_crumb(session)
            if crumb:
                params["crumb"] = crumb
                response = session.get(url, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            result = data['chart']['result'][0]
            
            timestamps = result['timestamp']
            quote = result['indicators']['quote'][0]
            
            df = pd.DataFrame({
                'Open': quote['open'],
                'High': quote['high'],
                'Low': quote['low'],
                'Close': quote['close'],
                'Volume': quote['volume']
            }, index=pd.to_datetime(timestamps, unit='s'))
            
            df.index.name = 'Date'
            df = df.dropna(subset=['Close'])
            return df
    except Exception:
        pass
    
    return None

def _fetch_from_yfinance(ticker, period="2y"):
    """Fallback to yfinance which handles cookies/crumb internally."""
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        df.index.name = "Date"
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(subset=['Close'])
        return df
    except Exception:
        return None

def _compute_indicators(df):
    """Add derived indicators to a stock dataframe."""
    # MA
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp12 - exp26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # Bollinger Bands (20, 2)
    df['BB_Middle'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['BB_Middle'] + (2 * df['BB_Std'])
    df['BB_Lower'] = df['BB_Middle'] - (2 * df['BB_Std'])
    
    # Distance
    df['Dist_MA200_Pct'] = ((df['Close'] - df['SMA_200']) / df['SMA_200'])
    return df

@st.cache_data(ttl=3600)  # Cache data for 1 hour
def get_stock_data(tickers, period="2y"):
    """
    Fetches historical data for a list of tickers.
    Tries Yahoo Chart API with crumb, then falls back to yfinance.
    """
    data = {}
    session = _get_yahoo_session()
    crumb = None
    
    # Use Yahoo Chart API directly for each ticker; fallback to yfinance if needed
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
        
        time.sleep(0.3)  # Small delay between requests to avoid rate limiting
    
    return data

@st.cache_data(ttl=3600)
def get_fear_and_greed():
    """
    Fetches CNN Fear & Greed Index. 
    Uses multiple fallback mechanisms.
    """
    # Method 1: Try CNN API
    urls = [
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        "https://production.dataviz.cnn.io/index/fearandgreed/current",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.cnn.com/markets/fear-and-greed"
    }
    
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if 'fear_and_greed' in data:
                    fng_value = data['fear_and_greed']['score']
                    fng_rating = data['fear_and_greed']['rating']
                    return float(fng_value), fng_rating
                elif 'score' in data:
                    return float(data['score']), data.get('rating', 'Unknown')
        except Exception:
            continue
    
    # Method 2: Alternative Fear & Greed API
    try:
        alt_url = "https://api.alternative.me/fng/?limit=1"
        r = requests.get(alt_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if 'data' in data and len(data['data']) > 0:
                fng_value = int(data['data'][0]['value'])
                fng_rating = data['data'][0]['value_classification']
                return fng_value, fng_rating
    except Exception:
        pass
    
    return None, "数据获取失败"

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
    target_etfs = ['VOO', 'QQQ', 'SMH', 'TLT']
    macro_tickers = ['^VIX', '^TNX'] # VIX, 10Y Yield
    
    selected_etf = st.sidebar.selectbox("选择详情分析标的", target_etfs)
    time_range = st.sidebar.radio("时间范围", ["1y", "2y", "5y"], index=1)
    
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
        summary_df.style.applymap(highlight_rsi, subset=['RSI (14)']),
        use_container_width=True,
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

if __name__ == "__main__":
    main()
