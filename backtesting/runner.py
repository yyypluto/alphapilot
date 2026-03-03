"""
CLI runner for the backtesting framework.

Usage:
    python -m backtesting.runner --strategy pmcc --years 10
    python -m backtesting.runner --strategy put_credit_spread --years 5
    python -m backtesting.runner --strategy wheel --years 10
    python -m backtesting.runner --all --years 5
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from backtesting.data import fetch_backtest_data
from backtesting.engine import BacktestEngine, Portfolio
from backtesting.metrics import compute_metrics, format_report
from backtesting.visualizer import (
    OUTPUT_DIR,
    plot_equity_curves,
    plot_monthly_heatmap,
    print_comparison_table,
)

# Strategy registry
STRATEGIES = {
    "pmcc": {
        "name": "PMCC (LEAPS Diagonal)",
        "ticker": "QQQ",
        "tickers_needed": ["QQQ"],
        "iv_scale": 1.15,
    },
    "put_credit_spread": {
        "name": "Put Credit Spread",
        "ticker": "QQQ",
        "tickers_needed": ["QQQ"],
        "iv_scale": 1.15,
    },
    "wheel": {
        "name": "Wheel (SCHG)",
        "ticker": "SCHG",
        "tickers_needed": ["SCHG"],
        "iv_scale": 1.20,
    },
    "hydra_pmcc": {
        "name": "Hydra(Simple) + PMCC",
        "ticker": "QQQ",
        "tickers_needed": ["QQQ", "GLD"],
        "iv_scale": 1.15,
    },
    "hydra_pmcc_soxx": {
        "name": "Hydra(SOXX) + PMCC",
        "ticker": "QQQ",
        "tickers_needed": ["QQQ", "GLD", "SOXX"],
        "iv_scale": 1.15,
    },
    "hydra_v6": {
        "name": "Hydra V6 ETF Rotation",
        "ticker": "QQQ",
        "tickers_needed": ["QQQ", "QLD", "GLD", "SOXX"],
        "iv_scale": 1.0,
    },
}


def _create_strategy(name: str):
    """Factory to create strategy instances."""
    if name == "pmcc":
        from backtesting.strategies.pmcc import PMCCStrategy
        return PMCCStrategy(ticker="QQQ")
    elif name == "put_credit_spread":
        from backtesting.strategies.put_credit_spread import PutCreditSpreadStrategy
        return PutCreditSpreadStrategy(ticker="QQQ")
    elif name == "wheel":
        from backtesting.strategies.wheel import WheelStrategy
        return WheelStrategy(ticker="SCHG")
    elif name == "hydra_pmcc":
        from backtesting.strategies.hydra_pmcc import HydraPMCCStrategy
        return HydraPMCCStrategy(ticker="QQQ", state_mode="simple")
    elif name == "hydra_pmcc_soxx":
        from backtesting.strategies.hydra_pmcc import HydraPMCCStrategy
        return HydraPMCCStrategy(ticker="QQQ", state_mode="soxx")
    elif name == "hydra_v6":
        from backtesting.strategies.hydra_v6 import HydraV6Strategy
        return HydraV6Strategy(ticker="QQQ")
    else:
        raise ValueError(f"Unknown strategy: {name}")


def _create_benchmark(ticker: str):
    from backtesting.strategies.buy_and_hold import BuyAndHoldStrategy
    return BuyAndHoldStrategy(ticker=ticker)


def run_single_strategy(
    strategy_key: str,
    data: pd.DataFrame,
    initial_cash: float = 100_000.0,
) -> Tuple[Portfolio, Dict]:
    """Run a single strategy and return portfolio + metrics."""
    config = STRATEGIES[strategy_key]
    strategy = _create_strategy(strategy_key)
    ticker = config["ticker"]

    print(f"\n🚀 运行策略: {config['name']} (标的: {ticker})")
    print("-" * 50)

    engine = BacktestEngine(
        data=data,
        strategy=strategy,
        initial_cash=initial_cash,
        iv_scale=config["iv_scale"],
    )
    portfolio = engine.run()

    # Get equity curve
    equity = portfolio.get_equity_curve()

    # Compute benchmark
    benchmark_strategy = _create_benchmark(ticker)
    bench_engine = BacktestEngine(
        data=data,
        strategy=benchmark_strategy,
        initial_cash=initial_cash,
        iv_scale=config["iv_scale"],
    )
    bench_portfolio = bench_engine.run()
    benchmark_equity = bench_portfolio.get_equity_curve()

    # Average RFR for metrics
    avg_rfr = data["RFR"].mean() if "RFR" in data.columns else 0.04

    # Metrics
    metrics = compute_metrics(
        equity,
        trades=portfolio.trades,
        rfr=avg_rfr,
        benchmark=benchmark_equity,
    )

    # Print report
    report = format_report(metrics, config["name"])
    print(report)

    return portfolio, metrics, equity, benchmark_equity


def main():
    parser = argparse.ArgumentParser(
        description="AlphaPilot Options Backtesting Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m backtesting.runner --strategy pmcc --years 5
  python -m backtesting.runner --strategy wheel --years 10
  python -m backtesting.runner --all --years 5
        """,
    )
    parser.add_argument(
        "--strategy",
        choices=list(STRATEGIES.keys()),
        help="要回测的策略",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="运行所有策略并对比",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="回测年数 (默认: 5)",
    )
    parser.add_argument(
        "--cash",
        type=float,
        default=100_000.0,
        help="初始资金 (默认: $100,000)",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="跳过图表生成",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="强制重新下载数据（忽略缓存）",
    )

    args = parser.parse_args()

    if not args.strategy and not args.all:
        parser.print_help()
        print("\n❌ 请指定 --strategy 或 --all")
        sys.exit(1)

    # Determine which tickers we need
    if args.all:
        strategies_to_run = list(STRATEGIES.keys())
    else:
        strategies_to_run = [args.strategy]

    all_tickers = set()
    for sk in strategies_to_run:
        all_tickers.update(STRATEGIES[sk]["tickers_needed"])
    all_tickers = sorted(all_tickers)

    # Fetch data
    print(f"\n{'='*60}")
    print(f"📊 AlphaPilot 期权回测框架")
    print(f"{'='*60}")
    print(f"  回测周期: {args.years} 年")
    print(f"  初始资金: ${args.cash:,.0f}")
    print(f"  策略:     {', '.join(strategies_to_run)}")
    print(f"  标的:     {', '.join(all_tickers)}")
    print(f"{'='*60}")

    data = fetch_backtest_data(
        tickers=all_tickers,
        years=args.years,
        force_refresh=args.force_refresh,
    )

    # Run strategies
    all_equity_curves = {}
    all_metrics = {}
    benchmark_curves = {}

    for sk in strategies_to_run:
        portfolio, metrics, equity, bench_equity = run_single_strategy(
            sk, data, initial_cash=args.cash
        )
        all_equity_curves[STRATEGIES[sk]["name"]] = equity
        all_metrics[STRATEGIES[sk]["name"]] = metrics

        bench_name = f"Buy & Hold {STRATEGIES[sk]['ticker']}"
        if bench_name not in benchmark_curves:
            benchmark_curves[bench_name] = bench_equity

    # Comparison table
    if len(all_metrics) > 1:
        print_comparison_table(all_metrics)

    # Plots
    if not args.no_plot:
        # Combine strategy + benchmark curves
        all_curves = {**all_equity_curves, **benchmark_curves}

        plot_equity_curves(
            all_curves,
            title=f"Strategy Comparison — {args.years}Y Backtest (${args.cash:,.0f} Initial Capital)",
            save_path=str(OUTPUT_DIR / f"equity_curves_{args.years}y.png"),
        )

        # Monthly heatmap for each strategy
        for name, equity in all_equity_curves.items():
            safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").lower()
            plot_monthly_heatmap(
                equity,
                strategy_name=name,
                save_path=str(OUTPUT_DIR / f"monthly_{safe_name}_{args.years}y.png"),
            )

    print(f"\n✅ 回测完成！图表保存在: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
