-- Create market_daily_metrics table
CREATE TABLE IF NOT EXISTS market_daily_metrics (
    date DATE NOT NULL,
    ticker TEXT NOT NULL,
    close NUMERIC,
    rsi_14 NUMERIC,
    ma200_dist_pct NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    PRIMARY KEY (date, ticker)
);

-- Create macro_indicators table
CREATE TABLE IF NOT EXISTS macro_indicators (
    date DATE PRIMARY KEY,
    vix_close NUMERIC,
    fear_greed_index INTEGER,
    us10y_yield NUMERIC,
    soxx_qqq_ratio NUMERIC,
    xlp_xly_ratio NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

