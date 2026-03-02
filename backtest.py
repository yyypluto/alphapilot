import time
import datetime as dt

import yfinance as yf
import pandas as pd
import numpy as np

try:
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import seaborn as sns
except ImportError:
    sns = None

# ---------------------------------------------------------
# 1. 数据准备 (Data Fetching)
# ---------------------------------------------------------
print("🚀 正在下载历史数据 (QQQ, SOXX, QLD, GLD)...")
tickers = ['QQQ', 'SOXX', 'QLD', 'GLD']

# 回测区间：尽量拉长到近 20 年（不足 20 年则以可获取数据为准）
end_date_dt = dt.date.today()
start_date_dt = dt.date(end_date_dt.year - 20, end_date_dt.month, min(end_date_dt.day, 28))
start_date = start_date_dt.isoformat()
end_date = end_date_dt.isoformat()

# 一次性下载，使用 'Adj Close' (复权收盘价) 以包含分红
# yfinance 有频率限制：做一个简单重试 + 本地缓存兜底
CACHE_CSV = 'backtest_prices_adj_close.csv'


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors="coerce")
    df = df.sort_index()
    return df


def _covers_requested_range(df: pd.DataFrame, start: str, end: str) -> bool:
    """Return True if df roughly covers [start, end].

    We allow a small slack because markets don't trade every day, and
    some tickers may start a bit later.
    """
    if df is None or df.empty:
        return False
    df = _ensure_datetime_index(df)
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    # allow a few days slack on both ends
    slack = pd.Timedelta(days=10)
    return (df.index.min() <= start_dt + slack) and (df.index.max() >= end_dt - slack)


def fetch_from_stooq(symbol: str) -> pd.Series:
    """Fetch daily close prices from Stooq (free, no API key).

    Stooq provides CSV at: https://stooq.com/q/d/l/?s=SYMBOL&i=d
    For US ETFs, symbols are typically lower-case with .us suffix, e.g. qqq.us
    NOTE: Stooq close is already adjusted in many cases, but not guaranteed.
    We'll treat it as a fallback to get the script running when yfinance is rate-limited.
    """

    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    df = pd.read_csv(url)
    if df is None or df.empty:
        raise ValueError(f"Empty stooq data for {symbol}")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df.set_index("Date").sort_index()
    if "Close" not in df.columns:
        raise ValueError(f"Missing Close column for {symbol}")
    s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    return s


def fetch_prices_with_cache(max_retries: int = 2, sleep_seconds: int = 2) -> pd.DataFrame:
    # Prefer cache first to avoid yfinance rate limits during iterative research,
    # but ONLY if it covers the requested time range.
    try:
        out = pd.read_csv(CACHE_CSV, index_col=0, parse_dates=True)
        out = _ensure_datetime_index(out)

        if not out.empty:
            missing = [t for t in tickers if t not in out.columns]

            # If cache is missing tickers, patch them first.
            if missing:
                try:
                    mapping = {"QQQ": "qqq.us", "SOXX": "soxx.us", "QLD": "qld.us", "GLD": "gld.us"}
                    patched = out.copy()
                    for t in missing:
                        patched[t] = fetch_from_stooq(mapping[t])
                    patched = _ensure_datetime_index(patched)
                    patched.to_csv(CACHE_CSV)
                    print(f"⚠️ 已补全缓存缺失列 {missing} 并更新: {CACHE_CSV}")
                    out = patched
                except Exception:
                    # If patching fails, fall through to online fetch
                    pass

            # Do not drop rows with partial NaNs here, otherwise early history gets truncated
            if not out.empty and not [t for t in tickers if t not in out.columns]:
                if _covers_requested_range(out, start_date, end_date):
                    return out
                print(
                    f"⚠️ 缓存数据范围不足({out.index.min().date()} - {out.index.max().date()})，将尝试拉取更长区间..."
                )
    except Exception:
        pass

    last_err = None
    for i in range(max_retries):
        try:
            df = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                auto_adjust=False,
                progress=True,
            )
            if df is None or df.empty:
                raise ValueError('Empty data from yfinance')

            if 'Adj Close' not in df.columns:
                raise ValueError('Missing Adj Close in yfinance response')

            out = df['Adj Close']
            if not out.empty:
                out.to_csv(CACHE_CSV)
                return out
        except Exception as e:
            last_err = e
            if i < max_retries - 1:
                time.sleep(sleep_seconds)

    # Fallback to cache
    try:
        out = pd.read_csv(CACHE_CSV, index_col=0, parse_dates=True)
        out = _ensure_datetime_index(out)
        if not out.empty:
            print(f"⚠️ yfinance 下载失败，已使用本地缓存: {CACHE_CSV}")
            return out
    except Exception:
        pass

    # Fallback to Stooq (network required)
    try:
        print("⚠️ yfinance 被限流且无本地缓存，尝试使用 Stooq 数据源...")
        mapping = {"QQQ": "qqq.us", "SOXX": "soxx.us", "QLD": "qld.us", "GLD": "gld.us"}
        series = {}
        for t in tickers:
            series[t] = fetch_from_stooq(mapping[t])
        out = pd.concat(series, axis=1)
        out = _ensure_datetime_index(out)
        out = out.loc[start_date:end_date]
        if not out.empty:
            out.to_csv(CACHE_CSV)
            print(f"✅ 已从 Stooq 获取数据，并写入缓存: {CACHE_CSV}")
            return out
    except Exception as e:
        last_err = e

    raise RuntimeError(f"Failed to fetch data from yfinance and no cache available. Last error: {last_err}")


data = fetch_prices_with_cache()

# Use the actual data range for reporting/plotting (ignore all-NaN rows).
if data is not None and not data.empty:
    valid_index = data.dropna(how="all").index
    if len(valid_index) > 0:
        actual_start = valid_index.min().date().isoformat()
        actual_end = valid_index.max().date().isoformat()
    else:
        actual_start = start_date
        actual_end = end_date
else:
    actual_start = start_date
    actual_end = end_date

# Toggle for plotting behavior
SHOW_PLOT = False  # set True if you want an interactive window
PLOT_PATH = "backtest_v6_gld_equity_curve.png"
STATE_PLOT_PATH = "backtest_v6_gld_stage_transitions.png"

# ---------------------------------------------------------
# 2. 信号计算 (State Machine) - V5.0 + Ladder Buy
# ---------------------------------------------------------
window = 60

# 1) 基础指标
data['QQQ_MA200'] = data['QQQ'].rolling(window=200).mean()

roll_max_qqq = data['QQQ'].rolling(window=window).max()
roll_max_soxx = data['SOXX'].rolling(window=window).max()

data['DD_QQQ'] = (data['QQQ'] - roll_max_qqq) / roll_max_qqq
data['DD_SOXX'] = (data['SOXX'] - roll_max_soxx) / roll_max_soxx

# 2) 状态机：0=Attack(QLD), 1=Defense(QQQ), 2=Escape(Cash/GLD + Ladder Buy)
# 说明：np.select 会按顺序优先匹配前面的条件。
conditions = [
    (data['QQQ'] < data['QQQ_MA200']),
    (data['DD_QQQ'] < -0.04),
    (data['DD_QQQ'] > -0.04) & (data['DD_SOXX'].notna()) & (data['DD_SOXX'] < -0.10),
    (data['DD_QQQ'] > -0.02) & (data['DD_SOXX'].notna()) & (data['DD_SOXX'] < -0.05),
]
choices = [2, 1, 2, 1]
default = 0

raw_state = np.select(conditions, choices, default=default)
state_series = pd.Series(raw_state, index=data.index).shift(1)  # 滞后一天执行

# ---------------------------------------------------------
# 3. 动态仓位逻辑 (The Ladder Logic)
# ---------------------------------------------------------
# 记录每天持有: [QQQ, QLD, GLD, Cash]
positions = []

for i in range(len(data)):
    state = state_series.iloc[i]
    current_dd = data['DD_QQQ'].iloc[i]

    pct_qqq = 0.0
    pct_qld = 0.0
    pct_gld = 0.0
    pct_cash = 0.0

    if state == 0:
        pct_qld = 1.0
    elif state == 1:
        pct_qqq = 1.0
    else:
        # state == 2: 反脆弱 Hydra 模式
        # 固定配置：20% GLD（黄金避险）
        base_gld = 0.20

        dip_allocation = 0.0
        if pd.notna(current_dd):
            if current_dd < -0.30:
                dip_allocation = 0.80
            elif current_dd < -0.20:
                dip_allocation = 0.50
            elif current_dd < -0.10:
                dip_allocation = 0.20

        pct_qqq = dip_allocation
        pct_gld = base_gld
        pct_cash = 1.0 - pct_qqq - pct_gld

    positions.append([pct_qqq, pct_qld, pct_gld, pct_cash])

pos_df = pd.DataFrame(positions, columns=['QQQ', 'QLD', 'GLD', 'Cash'], index=data.index)

# ---------------------------------------------------------
# 4. 收益计算
# ---------------------------------------------------------
ret_qqq = data['QQQ'].pct_change().fillna(0.0)
ret_qld = data['QLD'].pct_change().fillna(0.0)
ret_gld = data['GLD'].pct_change().fillna(0.0)
ret_cash = 0.03 / 252

strat_ret = (
    pos_df['QQQ'].shift(1).fillna(0.0) * ret_qqq
    + pos_df['QLD'].shift(1).fillna(0.0) * ret_qld
    + pos_df['GLD'].shift(1).fillna(0.0) * ret_gld
    + pos_df['Cash'].shift(1).fillna(1.0) * ret_cash
)

strategy_cum_ret = (1 + strat_ret).cumprod().values
strat_cum_series = pd.Series(strategy_cum_ret, index=data.index)

qld_cum_ret = (1 + ret_qld).cumprod()
qqq_cum_ret = (1 + ret_qqq).cumprod()
gld_cum_ret = (1 + ret_gld).cumprod()

# ---------------------------------------------------------
# 4. 绩效统计 (Performance Metrics)
# ---------------------------------------------------------
def get_max_drawdown(cum_ret_series):
    roll_max = cum_ret_series.cummax()
    drawdown = (cum_ret_series - roll_max) / roll_max
    return drawdown.min(), drawdown

# 计算回撤
strat_dd_min, strat_dd_curve = get_max_drawdown(strat_cum_series)
qld_dd_min, qld_dd_curve = get_max_drawdown(qld_cum_ret)
qqq_dd_min, qqq_dd_curve = get_max_drawdown(qqq_cum_ret)
gld_dd_min, gld_dd_curve = get_max_drawdown(gld_cum_ret)

# 计算总回报
if len(strategy_cum_ret) == 0:
    raise RuntimeError("No strategy return series computed (empty data).")

strat_total_ret = float(strategy_cum_ret[-1]) - 1
qld_total_ret = float(qld_cum_ret.iloc[-1]) - 1
qqq_total_ret = float(qqq_cum_ret.iloc[-1]) - 1
gld_total_ret = float(gld_cum_ret.iloc[-1]) - 1

print(f"\n====== 📊 回测报告 (数据实际覆盖: {actual_start} - {actual_end}; 目标区间: {start_date} - {end_date}) ======")
print(f"策略总回报: {strat_total_ret*100:.2f}%")
print(f"QLD(死拿)总回报: {qld_total_ret*100:.2f}%")
print(f"QQQ(死拿)总回报: {qqq_total_ret*100:.2f}%")
print(f"GLD(死拿)总回报: {gld_total_ret*100:.2f}%")
print(f"------------------------------------")
print(f"策略最大回撤: {strat_dd_min*100:.2f}%")
print(f"QLD(死拿)最大回撤: {qld_dd_min*100:.2f}%")
print(f"QQQ(基准)最大回撤: {qqq_dd_min*100:.2f}%")
print(f"GLD(基准)最大回撤: {gld_dd_min*100:.2f}%")

# 状态切换点（用于绘图标注）
state_series_clean = state_series.copy()
state_change_mask = state_series_clean.ne(state_series_clean.shift(1)) & state_series_clean.notna()
state_change_dates = state_series_clean.index[state_change_mask]
state_change_states = state_series_clean[state_change_mask].astype(int)

# ---------------------------------------------------------
# 4.5 多周期收益对比表 (20Y / 10Y / 5Y)
# ---------------------------------------------------------
def _slice_by_years(series: pd.Series, years: int) -> pd.Series:
    if series is None or series.empty:
        return series
    end_dt = series.index.max()
    start_dt = end_dt - pd.DateOffset(years=years)
    sliced = series.loc[start_dt:end_dt]
    return sliced


def _total_return(series: pd.Series) -> float:
    if series is None or series.empty:
        return float("nan")
    return float(series.iloc[-1] / series.iloc[0] - 1)


periods = [20, 10, 5]
return_rows = []
for years in periods:
    strat_slice = _slice_by_years(strat_cum_series, years)
    qld_slice = _slice_by_years(qld_cum_ret, years)
    qqq_slice = _slice_by_years(qqq_cum_ret, years)
    gld_slice = _slice_by_years(gld_cum_ret, years)

    return_rows.append(
        {
            "Period": f"{years}Y -> Now",
            "Strategy": _total_return(strat_slice),
            "QLD": _total_return(qld_slice),
            "QQQ": _total_return(qqq_slice),
            "GLD": _total_return(gld_slice),
        }
    )

return_table = pd.DataFrame(return_rows)
print("\n====== 📌 多周期收益对比 ======")
print(return_table.to_string(index=False, formatters={
    "Strategy": lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A",
    "QLD": lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A",
    "QQQ": lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A",
    "GLD": lambda x: f"{x*100:.2f}%" if pd.notna(x) else "N/A",
}))

# ---------------------------------------------------------
# 5. 可视化 (Visualization)
# ---------------------------------------------------------
if plt is None:
    print("\n⚠️ matplotlib 未安装，跳过画图。")
    raise SystemExit(0)

try:
    plt.style.use("seaborn-v0_8-whitegrid")
except Exception:
    pass

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.labelsize": 11,
})

plt.figure(figsize=(14, 8))

# 上图：净值曲线
plt.subplot(2, 1, 1)
plt.plot(strat_cum_series, label='V6 Hydra Strategy', color='#7c3aed', linewidth=2.2)
plt.plot(qld_cum_ret, label='Buy & Hold QLD', color='gray', alpha=0.5, linestyle='--')
plt.plot(qqq_cum_ret, label='Buy & Hold QQQ', color='green', alpha=0.5)
plt.plot(gld_cum_ret, label='Buy & Hold GLD', color='#f59e0b', alpha=0.65)

# 标注状态切换点
state_marker_cfg = {
    0: {"label": "Stage 0 (QLD)", "color": "#16a34a", "marker": "^"},
    1: {"label": "Stage 1 (QQQ)", "color": "#f59e0b", "marker": "o"},
    2: {"label": "Stage 2 (GLD)", "color": "#ef4444", "marker": "v"},
}
for state_id, cfg in state_marker_cfg.items():
    idx = state_change_dates[state_change_states == state_id]
    if len(idx) > 0:
        plt.scatter(
            idx,
            strat_cum_series.loc[idx],
            s=30,
            color=cfg["color"],
            marker=cfg["marker"],
            edgecolor="white",
            linewidth=0.6,
            alpha=0.9,
            label=cfg["label"],
            zorder=5,
        )

plt.title(f'V6 Hydra Strategy vs Benchmarks (Log Scale)\n{actual_start} - {actual_end}')
plt.yscale('log') # 对数坐标看长期增长更清晰
plt.legend()
plt.grid(True, which="both", ls="-", alpha=0.2)

# 下图：回撤曲线
plt.subplot(2, 1, 2)
plt.plot(strat_dd_curve, label='Strategy Drawdown', color='red', linewidth=1)
plt.plot(qld_dd_curve, label='QLD Drawdown', color='gray', alpha=0.3)
plt.fill_between(strat_dd_curve.index, strat_dd_curve, 0, color='red', alpha=0.1)
plt.title('Drawdown Analysis')
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()
if SHOW_PLOT:
    plt.show()
else:
    plt.savefig(PLOT_PATH, dpi=160, bbox_inches="tight")
    print(f"\n🖼️ 已输出图表: {PLOT_PATH}")

# 单独绘制状态切换图（放大）
fig, ax = plt.subplots(figsize=(16, 5))
ax.plot(strat_cum_series, color="#7c3aed", linewidth=1.5, alpha=0.6, label="Strategy")
for state_id, cfg in state_marker_cfg.items():
    idx = state_change_dates[state_change_states == state_id]
    if len(idx) > 0:
        ax.scatter(
            idx,
            strat_cum_series.loc[idx],
            s=60,
            color=cfg["color"],
            marker=cfg["marker"],
            edgecolor="white",
            linewidth=0.8,
            alpha=0.95,
            label=cfg["label"],
            zorder=5,
        )
ax.set_title(f"Stage Transitions (Zoomed)\n{actual_start} - {actual_end}")
ax.set_yscale("log")
ax.grid(True, which="both", ls="-", alpha=0.25)
ax.legend(ncol=3, loc="upper left", frameon=False)
fig.tight_layout()

if SHOW_PLOT:
    plt.show()
else:
    fig.savefig(STATE_PLOT_PATH, dpi=180, bbox_inches="tight")
    print(f"🖼️ 已输出切换图: {STATE_PLOT_PATH}")