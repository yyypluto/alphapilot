"""
Performance metrics for backtesting.

Computes standard quantitative metrics from an equity curve and trade list.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def total_return(equity: pd.Series) -> float:
    """Total cumulative return as a decimal (e.g. 1.5 = +150%)."""
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def cagr(equity: pd.Series) -> float:
    """Compound Annual Growth Rate."""
    if equity.empty or len(equity) < 2:
        return 0.0
    total_ret = equity.iloc[-1] / equity.iloc[0]
    n_days = (equity.index[-1] - equity.index[0]).days
    if n_days <= 0:
        return 0.0
    years = n_days / 365.25
    return float(total_ret ** (1.0 / years) - 1)


def max_drawdown(equity: pd.Series) -> Tuple[float, pd.Series]:
    """
    Maximum drawdown from peak.

    Returns:
        (max_dd_value, drawdown_series)
        max_dd_value is negative (e.g. -0.35 = -35%)
    """
    if equity.empty:
        return 0.0, pd.Series(dtype=float)
    rolling_max = equity.cummax()
    dd = (equity - rolling_max) / rolling_max
    return float(dd.min()), dd


def sharpe_ratio(
    equity: pd.Series, rfr: float = 0.04, periods_per_year: int = 252
) -> float:
    """
    Annualized Sharpe Ratio.

    Args:
        equity: daily NAV series
        rfr: annualized risk-free rate
        periods_per_year: trading days per year
    """
    if len(equity) < 2:
        return 0.0
    daily_returns = equity.pct_change().dropna()
    if daily_returns.std() == 0:
        return 0.0
    daily_rfr = rfr / periods_per_year
    excess = daily_returns - daily_rfr
    return float(
        np.sqrt(periods_per_year) * excess.mean() / excess.std()
    )


def sortino_ratio(
    equity: pd.Series, rfr: float = 0.04, periods_per_year: int = 252
) -> float:
    """Annualized Sortino Ratio (downside deviation only)."""
    if len(equity) < 2:
        return 0.0
    daily_returns = equity.pct_change().dropna()
    daily_rfr = rfr / periods_per_year
    excess = daily_returns - daily_rfr
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float(
        np.sqrt(periods_per_year) * excess.mean() / downside.std()
    )


def calmar_ratio(equity: pd.Series) -> float:
    """CAGR / |MaxDrawdown|. Higher is better."""
    c = cagr(equity)
    mdd, _ = max_drawdown(equity)
    if mdd == 0:
        return float("inf") if c > 0 else 0.0
    return float(c / abs(mdd))


def win_rate(trades: list) -> float:
    """Percentage of profitable trades."""
    realized = [t for t in trades if hasattr(t, "pnl") and t.pnl != 0]
    if not realized:
        return 0.0
    winners = sum(1 for t in realized if t.pnl > 0)
    return winners / len(realized)


def profit_factor(trades: list) -> float:
    """Gross profit / Gross loss."""
    gross_profit = sum(t.pnl for t in trades if hasattr(t, "pnl") and t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if hasattr(t, "pnl") and t.pnl < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def avg_win_loss(trades: list) -> Tuple[float, float]:
    """Average winning trade P&L and average losing trade P&L."""
    winners = [t.pnl for t in trades if hasattr(t, "pnl") and t.pnl > 0]
    losers = [t.pnl for t in trades if hasattr(t, "pnl") and t.pnl < 0]
    avg_win = np.mean(winners) if winners else 0.0
    avg_loss = np.mean(losers) if losers else 0.0
    return float(avg_win), float(avg_loss)


def monthly_returns(equity: pd.Series) -> pd.DataFrame:
    """
    Monthly returns table (rows=year, columns=month).
    Values are in percent.
    """
    if equity.empty:
        return pd.DataFrame()
    monthly = equity.resample("ME").last().pct_change().dropna()
    df = pd.DataFrame(
        {
            "Year": monthly.index.year,
            "Month": monthly.index.month,
            "Return": monthly.values * 100,
        }
    )
    pivot = df.pivot_table(index="Year", columns="Month", values="Return", aggfunc="sum")
    pivot.columns = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ][: len(pivot.columns)]
    return pivot


def compute_metrics(
    equity: pd.Series,
    trades: Optional[list] = None,
    rfr: float = 0.04,
    benchmark: Optional[pd.Series] = None,
) -> Dict:
    """
    Compute a full metrics report.

    Returns dict with all key metrics.
    """
    mdd_val, mdd_series = max_drawdown(equity)

    report = {
        "total_return": total_return(equity),
        "cagr": cagr(equity),
        "max_drawdown": mdd_val,
        "sharpe_ratio": sharpe_ratio(equity, rfr),
        "sortino_ratio": sortino_ratio(equity, rfr),
        "calmar_ratio": calmar_ratio(equity),
    }

    if trades:
        report["win_rate"] = win_rate(trades)
        report["profit_factor"] = profit_factor(trades)
        avg_w, avg_l = avg_win_loss(trades)
        report["avg_win"] = avg_w
        report["avg_loss"] = avg_l
        report["total_trades"] = len([t for t in trades if t.pnl != 0])

    if benchmark is not None and not benchmark.empty:
        report["benchmark_total_return"] = total_return(benchmark)
        report["benchmark_cagr"] = cagr(benchmark)
        bm_mdd, _ = max_drawdown(benchmark)
        report["benchmark_max_drawdown"] = bm_mdd
        report["benchmark_sharpe"] = sharpe_ratio(benchmark, rfr)

    return report


def format_report(metrics: Dict, strategy_name: str = "Strategy") -> str:
    """Format metrics dict into a readable console report."""
    lines = [
        f"\n{'='*60}",
        f"📊 {strategy_name} — 回测报告",
        f"{'='*60}",
    ]

    lines.append(f"  总回报:      {metrics.get('total_return', 0)*100:>10.2f}%")
    lines.append(f"  年化收益:    {metrics.get('cagr', 0)*100:>10.2f}%")
    lines.append(f"  最大回撤:    {metrics.get('max_drawdown', 0)*100:>10.2f}%")
    lines.append(f"  夏普比率:    {metrics.get('sharpe_ratio', 0):>10.2f}")
    lines.append(f"  索提诺比率:  {metrics.get('sortino_ratio', 0):>10.2f}")
    lines.append(f"  卡尔玛比率:  {metrics.get('calmar_ratio', 0):>10.2f}")

    if "win_rate" in metrics:
        lines.append(f"\n  {'─'*40}")
        lines.append(f"  交易统计:")
        lines.append(f"  胜率:        {metrics.get('win_rate', 0)*100:>10.1f}%")
        lines.append(f"  盈亏比:      {metrics.get('profit_factor', 0):>10.2f}")
        lines.append(f"  平均盈利:    ${metrics.get('avg_win', 0):>10,.0f}")
        lines.append(f"  平均亏损:    ${metrics.get('avg_loss', 0):>10,.0f}")
        lines.append(f"  总交易数:    {metrics.get('total_trades', 0):>10d}")

    if "benchmark_total_return" in metrics:
        lines.append(f"\n  {'─'*40}")
        lines.append(f"  基准对比 (Buy & Hold):")
        lines.append(f"  基准总回报:  {metrics.get('benchmark_total_return', 0)*100:>10.2f}%")
        lines.append(f"  基准年化:    {metrics.get('benchmark_cagr', 0)*100:>10.2f}%")
        lines.append(f"  基准最大回撤:{metrics.get('benchmark_max_drawdown', 0)*100:>10.2f}%")
        lines.append(f"  基准夏普:    {metrics.get('benchmark_sharpe', 0):>10.2f}")

    lines.append(f"{'='*60}\n")
    return "\n".join(lines)
