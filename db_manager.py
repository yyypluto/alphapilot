import os
from typing import List, Optional

import pandas as pd
import streamlit as st
from supabase import create_client, Client


def init_supabase() -> Optional[Client]:
    """Initialize Supabase client from Streamlit secrets or Environment variables."""
    # Try getting secrets from Streamlit (Local/Cloud Dashboard)
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except (FileNotFoundError, KeyError):
        # Fallback to Environment Variables (GitHub Actions / Docker)
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        return None
        
    return create_client(url, key)

def fetch_market_daily(tickers: List[str], start: Optional[str] = None) -> pd.DataFrame:
    """Fetch market metrics for given tickers."""
    supabase = init_supabase()
    if not supabase:
        return pd.DataFrame()
    try:
        query = supabase.table("market_daily_metrics").select("*").in_("ticker", tickers)
        if start:
            query = query.gte("date", start)
        response = query.order("date", desc=False).execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as e:
        print(f"⚠️ DB fetch market_daily_metrics failed, fallback to API: {e}")
        return pd.DataFrame()

def fetch_macro(start: Optional[str] = None) -> pd.DataFrame:
    """Fetch macro indicators."""
    supabase = init_supabase()
    if not supabase:
        return pd.DataFrame()
    try:
        query = supabase.table("macro_indicators").select("*")
        if start:
            query = query.gte("date", start)
        response = query.order("date", desc=False).execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as e:
        print(f"⚠️ DB fetch macro_indicators failed, fallback to API: {e}")
        return pd.DataFrame()

def upsert_market_daily(data: List[dict]):
    """Insert or update market daily metrics."""
    supabase = init_supabase()
    if not supabase:
        return
        
    try:
        supabase.table("market_daily_metrics").upsert(data).execute()
        print(f"✅ Upserted {len(data)} rows to market_daily_metrics")
    except Exception as e:
        print(f"❌ Error upserting market data: {e}")

def upsert_macro(data: List[dict]):
    """Insert or update macro indicators."""
    supabase = init_supabase()
    if not supabase:
        return
        
    try:
        supabase.table("macro_indicators").upsert(data).execute()
        print(f"✅ Upserted {len(data)} rows to macro_indicators")
    except Exception as e:
        print(f"❌ Error upserting macro data: {e}")
