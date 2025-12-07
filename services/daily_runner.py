import sys
import os
import pandas as pd
import yfinance as yf
import requests
import json
from datetime import datetime, date

# Add parent directory to path to import config and db_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_manager import upsert_market_daily, upsert_macro
from config import TARGET_ETFS, MACRO_TICKERS, L1_TICKERS
from utils import get_fear_and_greed

# Tickers to watch
ALL_TICKERS = list(set(TARGET_ETFS + MACRO_TICKERS + L1_TICKERS))

def get_feishu_webhook():
    return os.getenv("FEISHU_WEBHOOK")

def send_feishu_alert(title, content):
    url = get_feishu_webhook()
    if not url:
        print("⚠️ No Feishu Webhook URL found.")
        return
        
    payload = {
        "msg_type": "text",
        "content": {
            "text": f"【AlphaPilot 监控报警】\n{title}\n\n{content}"
        }
    }
    try:
        requests.post(url, json=payload)
        print("✅ Feishu alert sent.")
    except Exception as e:
        print(f"❌ Failed to send Feishu alert: {e}")

def calculate_indicators(df):
    """Calculate RSI and MA200 dist."""
    if len(df) < 200:
        return None, None
        
    # RSI 14
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # MA200 Dist
    ma200 = df['Close'].rolling(window=200).mean()
    dist_pct = (df['Close'] - ma200) / ma200
    
    return rsi, dist_pct

def run_daily_job():
    print(f"🚀 Starting daily runner for {date.today()}...")
    
    # 1. Fetch Data
    print("📡 Fetching data from yfinance...")
    # Fetch 1 year data to ensure we have enough for MA200
    data = yf.download(ALL_TICKERS, period="1y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    
    market_metrics = []
    macro_data = {}
    today_str = date.today().isoformat()
    
    # Alerts container
    alerts = []

    # 2. Process Stock Data
    for ticker in ALL_TICKERS:
        try:
            if len(ALL_TICKERS) == 1:
                df = data
            else:
                df = data[ticker]
            
            if df.empty:
                continue
                
            # Drop NaNs
            df = df.dropna(subset=['Close'])
            if df.empty:
                continue

            latest = df.iloc[-1]
            latest_date = latest.name.date().isoformat() # Use the data's actual date
            
            # Calculate Indicators locally
            rsi_series, dist_series = calculate_indicators(df)
            
            rsi_val = rsi_series.iloc[-1] if rsi_series is not None else None
            dist_val = dist_series.iloc[-1] if dist_series is not None else None
            close_val = float(latest['Close'])

            # Store Market Metrics
            # Only store if it's a standard ETF (skip macro indices for this table if preferred, 
            # but schema allows all. We'll store all tickers in market_daily_metrics for simplicity)
            market_metrics.append({
                "date": latest_date,
                "ticker": ticker,
                "close": close_val,
                "rsi_14": float(rsi_val) if rsi_val and not pd.isna(rsi_val) else None,
                "ma200_dist_pct": float(dist_val) if dist_val and not pd.isna(dist_val) else None
            })
            
            # Check Alerts
            if rsi_val and rsi_val < 30 and ticker in ['VOO', 'QQQ', 'SMH', 'TLT']:
                alerts.append(f"🟢 {ticker} RSI 超卖 ({rsi_val:.1f})")

        except Exception as e:
            print(f"❌ Error processing {ticker}: {e}")

    # 3. Process Macro & L1 Indicators
    try:
        # Re-fetch latest Close for Ratio calculation (using aligned data)
        # Simplify: Just use the latest close we got from loop or access data directly
        def get_latest_close(t):
            try:
                return float(data[t]['Close'].iloc[-1])
            except:
                return None
        
        qqq = get_latest_close('QQQ')
        soxx = get_latest_close('SOXX')
        xlp = get_latest_close('XLP')
        xly = get_latest_close('XLY')
        vix = get_latest_close('^VIX')
        tnx = get_latest_close('^TNX')
        
        # Calculate Ratios
        soxx_qqq = soxx / qqq if soxx and qqq else None
        xlp_xly = xlp / xly if xlp and xly else None
        
        # Fear & Greed
        fng_score, _ = get_fear_and_greed()
        
        macro_record = {
            "date": today_str, # Macro uses run date usually, or latest data date
            "vix_close": vix,
            "fear_greed_index": int(fng_score) if fng_score else None,
            "us10y_yield": tnx,
            "soxx_qqq_ratio": soxx_qqq,
            "xlp_xly_ratio": xlp_xly
        }
        
        # Simple Divergence Alert Logic (Mockup: requires historical comparison)
        # Ideally we fetch last 5 days from DB to compare, but here we keep it simple for V2.0
        # You can expand this by fetching history from DB first.
        
        upsert_macro([macro_record])
        
    except Exception as e:
        print(f"❌ Error processing macro data: {e}")

    # 4. Save to DB
    if market_metrics:
        upsert_market_daily(market_metrics)

    # 5. Send Alerts
    if alerts:
        send_feishu_alert("每日收盘监控", "\n".join(alerts))
    else:
        print("✅ No alerts triggered today.")
    
    print("🎉 Daily runner finished successfully.")

if __name__ == "__main__":
    run_daily_job()
