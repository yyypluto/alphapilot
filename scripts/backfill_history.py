"""
历史数据回填脚本
将 Yahoo Finance 的历史数据批量导入到 Supabase 数据库
"""

import sys
import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_manager import init_supabase, upsert_market_daily, upsert_macro
from config import TARGET_ETFS, MACRO_TICKERS, L1_TICKERS

# 所有需要获取的 Tickers
ALL_TICKERS = list(set(TARGET_ETFS + MACRO_TICKERS + L1_TICKERS))

def fetch_yahoo_chart(ticker: str, period: str = "2y") -> pd.DataFrame:
    """通过 Yahoo Chart API 获取历史数据"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "range": period,
        "interval": "1d",
        "includePrePost": "false",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"  ❌ HTTP {response.status_code}")
            return pd.DataFrame()
        
        data = response.json()
        result = data["chart"]["result"][0]
        
        timestamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        
        df = pd.DataFrame({
            "Open": quote["open"],
            "High": quote["high"],
            "Low": quote["low"],
            "Close": quote["close"],
            "Volume": quote["volume"],
        }, index=pd.to_datetime(timestamps, unit="s"))
        
        df.index.name = "Date"
        return df.dropna(subset=["Close"])
    
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return pd.DataFrame()


def calculate_rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """计算 RSI"""
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_ma200_dist(df: pd.DataFrame) -> pd.Series:
    """计算 MA200 偏离度"""
    ma200 = df["Close"].rolling(window=200).mean()
    return (df["Close"] - ma200) / ma200


def backfill_market_data(period: str = "2y", batch_size: int = 500):
    """回填市场数据"""
    print("=" * 60)
    print("📊 开始回填市场数据")
    print(f"   Tickers: {ALL_TICKERS}")
    print(f"   周期: {period}")
    print("=" * 60)
    
    all_records = []
    
    for ticker in ALL_TICKERS:
        print(f"\n📡 获取 {ticker}...")
        df = fetch_yahoo_chart(ticker, period)
        
        if df.empty:
            print(f"  ⚠️ {ticker} 无数据，跳过")
            continue
        
        print(f"  ✅ 获取到 {len(df)} 条记录")
        
        # 计算指标
        df["RSI_14"] = calculate_rsi(df)
        df["MA200_Dist"] = calculate_ma200_dist(df)
        
        # 转换为数据库记录格式
        for date, row in df.iterrows():
            record = {
                "date": date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "close": float(row["Close"]) if pd.notna(row["Close"]) else None,
                "rsi_14": float(row["RSI_14"]) if pd.notna(row["RSI_14"]) else None,
                "ma200_dist_pct": float(row["MA200_Dist"]) if pd.notna(row["MA200_Dist"]) else None,
            }
            all_records.append(record)
        
        # 避免请求过快
        time.sleep(0.5)
    
    print(f"\n📝 总计 {len(all_records)} 条记录待写入")
    
    # 分批写入数据库
    print("\n💾 开始写入数据库...")
    for i in range(0, len(all_records), batch_size):
        batch = all_records[i:i + batch_size]
        upsert_market_daily(batch)
        print(f"   已写入 {min(i + batch_size, len(all_records))}/{len(all_records)}")
        time.sleep(0.2)  # 避免数据库压力过大
    
    print("\n✅ 市场数据回填完成!")
    return len(all_records)


def backfill_macro_data(period: str = "2y"):
    """回填宏观数据（VIX, TNX, Fear & Greed 等）"""
    print("\n" + "=" * 60)
    print("🌍 开始回填宏观数据")
    print("=" * 60)
    
    # 获取 VIX 数据
    print("\n📡 获取 VIX 数据...")
    vix_df = fetch_yahoo_chart("^VIX", period)
    
    # 获取 TNX (10年期国债收益率) 数据
    print("📡 获取 TNX 数据...")
    tnx_df = fetch_yahoo_chart("^TNX", period)
    
    # 获取 SOXX, QQQ, XLP, XLY 用于计算比率
    print("📡 获取 SOXX, QQQ, XLP, XLY 数据...")
    soxx_df = fetch_yahoo_chart("SOXX", period)
    qqq_df = fetch_yahoo_chart("QQQ", period)
    xlp_df = fetch_yahoo_chart("XLP", period)
    xly_df = fetch_yahoo_chart("XLY", period)
    
    # 构建日期索引（使用 VIX 的日期作为基准）
    if vix_df.empty:
        print("❌ VIX 数据获取失败，无法回填宏观数据")
        return 0
    
    macro_records = []
    
    for date in vix_df.index:
        date_str = date.strftime("%Y-%m-%d")
        
        # VIX
        vix_close = float(vix_df.loc[date, "Close"]) if date in vix_df.index else None
        
        # TNX
        tnx_close = None
        if not tnx_df.empty and date in tnx_df.index:
            tnx_close = float(tnx_df.loc[date, "Close"])
        
        # SOXX/QQQ 比率
        soxx_qqq = None
        if not soxx_df.empty and not qqq_df.empty:
            if date in soxx_df.index and date in qqq_df.index:
                soxx_close = float(soxx_df.loc[date, "Close"])
                qqq_close = float(qqq_df.loc[date, "Close"])
                if qqq_close > 0:
                    soxx_qqq = soxx_close / qqq_close
        
        # XLP/XLY 比率（防御/进攻）
        xlp_xly = None
        if not xlp_df.empty and not xly_df.empty:
            if date in xlp_df.index and date in xly_df.index:
                xlp_close = float(xlp_df.loc[date, "Close"])
                xly_close = float(xly_df.loc[date, "Close"])
                if xly_close > 0:
                    xlp_xly = xlp_close / xly_close
        
        record = {
            "date": date_str,
            "vix_close": vix_close,
            "us10y_yield": tnx_close,
            "soxx_qqq_ratio": soxx_qqq,
            "xlp_xly_ratio": xlp_xly,
            "fear_greed_index": None,  # Fear & Greed 无法获取历史数据，只能实时获取
        }
        macro_records.append(record)
    
    print(f"\n📝 总计 {len(macro_records)} 条宏观数据待写入")
    
    # 分批写入
    batch_size = 200
    print("\n💾 开始写入数据库...")
    for i in range(0, len(macro_records), batch_size):
        batch = macro_records[i:i + batch_size]
        upsert_macro(batch)
        print(f"   已写入 {min(i + batch_size, len(macro_records))}/{len(macro_records)}")
        time.sleep(0.2)
    
    print("\n✅ 宏观数据回填完成!")
    return len(macro_records)


def main():
    print("🚀 AlphaPilot 历史数据回填工具")
    print("=" * 60)
    
    # 检查数据库连接
    client = init_supabase()
    if not client:
        print("❌ 无法连接到 Supabase，请检查配置")
        return
    
    print("✅ Supabase 连接成功")
    
    # 设置回填周期
    period = "2y"  # 可选: "1y", "2y", "5y"
    
    # 回填市场数据
    market_count = backfill_market_data(period)
    
    # 回填宏观数据
    macro_count = backfill_macro_data(period)
    
    print("\n" + "=" * 60)
    print("🎉 数据回填完成!")
    print(f"   市场数据: {market_count} 条")
    print(f"   宏观数据: {macro_count} 条")
    print("=" * 60)


if __name__ == "__main__":
    main()
