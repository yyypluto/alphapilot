"""
Visualization module for backtest results.

Generates equity curves, drawdown charts, monthly heatmaps, and comparison tables.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from backtesting.metrics import max_drawdown, monthly_returns

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def plot_equity_curves(
    curves: Dict[str, pd.Series],
    title: str = "Strategy Comparison",
    save_path: Optional[str] = None,
    log_scale: bool = True,
) -> None:
    """
    Plot multiple equity curves on the same chart.

    Args:
        curves: dict of {name: equity_series}
        title: chart title
        save_path: file path to save (or None for show)
        log_scale: use log Y axis
    """
    if not HAS_MPL:
        print("⚠️ matplotlib 未安装，跳过绘图")
        return

    colors = ["#7c3aed", "#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6"]

    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except Exception:
        pass

    fig, axes = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={"height_ratios": [3, 1]})

    # ── Upper: Equity curves ──
    ax1 = axes[0]
    for i, (name, curve) in enumerate(curves.items()):
        color = colors[i % len(colors)]
        lw = 2.5 if i == 0 else 1.5
        alpha = 1.0 if i == 0 else 0.7
        ls = "-" if i < 2 else "--"
        ax1.plot(curve.index, curve.values, label=name, color=color, linewidth=lw, alpha=alpha, linestyle=ls)

    if log_scale:
        ax1.set_yscale("log")
    ax1.set_title(title, fontsize=15, fontweight="bold")
    ax1.legend(loc="upper left", frameon=True, framealpha=0.9)
    ax1.grid(True, which="both", ls="-", alpha=0.2)
    ax1.set_ylabel("Portfolio Value ($)")

    # Format y-axis as currency
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # ── Lower: Drawdown ──
    ax2 = axes[1]
    for i, (name, curve) in enumerate(curves.items()):
        color = colors[i % len(colors)]
        _, dd = max_drawdown(curve)
        alpha = 0.8 if i == 0 else 0.3
        ax2.plot(dd.index, dd.values * 100, label=name, color=color, linewidth=1, alpha=alpha)
        if i == 0:
            ax2.fill_between(dd.index, dd.values * 100, 0, color=color, alpha=0.15)

    ax2.set_title("Drawdown (%)", fontsize=12)
    ax2.set_ylabel("Drawdown %")
    ax2.legend(loc="lower left", fontsize=8, frameon=False)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=160, bbox_inches="tight")
        print(f"🖼️ 图表已保存: {save_path}")
    else:
        plt.show()
    plt.close(fig)


def plot_monthly_heatmap(
    equity: pd.Series,
    strategy_name: str = "Strategy",
    save_path: Optional[str] = None,
) -> None:
    """Plot monthly returns as a heatmap."""
    if not HAS_MPL:
        return

    monthly = monthly_returns(equity)
    if monthly.empty:
        return

    try:
        import seaborn as sns

        fig, ax = plt.subplots(figsize=(12, max(3, len(monthly) * 0.5)))
        sns.heatmap(
            monthly,
            annot=True,
            fmt=".1f",
            center=0,
            cmap="RdYlGn",
            linewidths=0.5,
            ax=ax,
            cbar_kws={"label": "Return (%)"},
        )
        ax.set_title(f"{strategy_name} — Monthly Returns (%)", fontsize=13, fontweight="bold")
        fig.tight_layout()

        if save_path:
            fig.savefig(save_path, dpi=160, bbox_inches="tight")
            print(f"🖼️ 热力图已保存: {save_path}")
        else:
            plt.show()
        plt.close(fig)
    except ImportError:
        print("⚠️ seaborn 未安装，跳过热力图")


def print_comparison_table(
    results: Dict[str, Dict],
) -> None:
    """Print a formatted comparison table of all strategy metrics."""
    headers = ["指标"]
    rows_data = {
        "总回报": [],
        "年化收益 (CAGR)": [],
        "最大回撤": [],
        "夏普比率": [],
        "索提诺比率": [],
        "卡尔玛比率": [],
        "胜率": [],
        "盈亏比": [],
        "交易次数": [],
    }

    for name, metrics in results.items():
        headers.append(name)
        rows_data["总回报"].append(f"{metrics.get('total_return', 0)*100:.1f}%")
        rows_data["年化收益 (CAGR)"].append(f"{metrics.get('cagr', 0)*100:.1f}%")
        rows_data["最大回撤"].append(f"{metrics.get('max_drawdown', 0)*100:.1f}%")
        rows_data["夏普比率"].append(f"{metrics.get('sharpe_ratio', 0):.2f}")
        rows_data["索提诺比率"].append(f"{metrics.get('sortino_ratio', 0):.2f}")
        rows_data["卡尔玛比率"].append(f"{metrics.get('calmar_ratio', 0):.2f}")
        rows_data["胜率"].append(
            f"{metrics.get('win_rate', 0)*100:.1f}%" if "win_rate" in metrics else "N/A"
        )
        rows_data["盈亏比"].append(
            f"{metrics.get('profit_factor', 0):.2f}" if "profit_factor" in metrics else "N/A"
        )
        rows_data["交易次数"].append(
            str(metrics.get("total_trades", 0)) if "total_trades" in metrics else "N/A"
        )

    # Calculate column widths
    col_widths = [max(len(h), 16) for h in headers]
    for key, vals in rows_data.items():
        col_widths[0] = max(col_widths[0], len(key) + 2)
        for i, v in enumerate(vals):
            col_widths[i + 1] = max(col_widths[i + 1], len(v) + 2)

    # Print
    sep = "+" + "+".join("-" * w for w in col_widths) + "+"
    print(f"\n{'='*60}")
    print("📊 策略对比总览")
    print(f"{'='*60}")
    print(sep)

    header_line = "|" + "|".join(h.center(w) for h, w in zip(headers, col_widths)) + "|"
    print(header_line)
    print(sep)

    for key, vals in rows_data.items():
        cells = [key.ljust(col_widths[0])]
        for v, w in zip(vals, col_widths[1:]):
            cells.append(v.rjust(w))
        print("|" + "|".join(cells) + "|")
    print(sep)


# ─────────────────────────────────────────────────────────
# Plotly Charts (for Streamlit / Web frontend)
# ─────────────────────────────────────────────────────────

PLOTLY_COLORS = ["#7c3aed", "#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6"]


def plotly_equity_chart(
    curves: Dict[str, pd.Series],
    title: str = "Strategy Comparison",
    log_scale: bool = True,
):
    """
    Create a Plotly figure with equity curves + drawdown subplot.

    Returns a plotly.graph_objects.Figure (can be passed to st.plotly_chart).
    """
    if not HAS_PLOTLY:
        return None

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("Portfolio Value ($)", "Drawdown (%)"),
    )

    for i, (name, curve) in enumerate(curves.items()):
        color = PLOTLY_COLORS[i % len(PLOTLY_COLORS)]
        lw = 2.5 if i == 0 else 1.5

        # Equity curve
        fig.add_trace(
            go.Scatter(
                x=curve.index, y=curve.values,
                name=name, line=dict(color=color, width=lw),
                hovertemplate=f"<b>{name}</b><br>%{{x|%Y-%m-%d}}<br>${{y:,.0f}}<extra></extra>",
            ),
            row=1, col=1,
        )

        # Drawdown
        _, dd = max_drawdown(curve)
        fig.add_trace(
            go.Scatter(
                x=dd.index, y=dd.values * 100,
                name=f"{name} DD", line=dict(color=color, width=1),
                showlegend=False,
                hovertemplate=f"<b>{name}</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.1f}}%<extra></extra>",
            ),
            row=2, col=1,
        )
        if i == 0:
            fig.add_trace(
                go.Scatter(
                    x=dd.index, y=dd.values * 100,
                    fill="tozeroy", fillcolor=f"rgba(124, 58, 237, 0.1)",
                    line=dict(width=0), showlegend=False,
                    hoverinfo="skip",
                ),
                row=2, col=1,
            )

    fig.update_layout(
        title=title,
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Lato, sans-serif", color="#64748b"),
        height=650,
        legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"),
        margin=dict(l=10, r=10, t=60, b=10),
        hovermode="x unified",
    )

    if log_scale:
        fig.update_yaxes(type="log", row=1, col=1)
    fig.update_xaxes(gridcolor="#f1f5f9", linecolor="#e2e8f0")
    fig.update_yaxes(gridcolor="#f1f5f9", linecolor="#e2e8f0")

    return fig


def plotly_monthly_heatmap(
    equity: pd.Series,
    strategy_name: str = "Strategy",
):
    """
    Create a Plotly heatmap of monthly returns.

    Returns a plotly.graph_objects.Figure.
    """
    if not HAS_PLOTLY:
        return None

    monthly = monthly_returns(equity)
    if monthly.empty:
        return None

    fig = go.Figure(
        data=go.Heatmap(
            z=monthly.values,
            x=monthly.columns.tolist(),
            y=[str(y) for y in monthly.index.tolist()],
            colorscale="RdYlGn",
            zmid=0,
            text=[[f"{v:.1f}%" for v in row] for row in monthly.values],
            texttemplate="%{text}",
            textfont={"size": 10},
            hovertemplate="%{y} %{x}<br>%{z:.1f}%<extra></extra>",
            colorbar=dict(title="Return %"),
        )
    )

    fig.update_layout(
        title=f"{strategy_name} — Monthly Returns (%)",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Lato, sans-serif", color="#64748b"),
        height=max(300, len(monthly) * 35 + 100),
        margin=dict(l=10, r=10, t=50, b=10),
        yaxis=dict(autorange="reversed"),
    )

    return fig

