"""
FastAPI REST API for the unified backtesting system.

Endpoints:
    GET  /api/strategies      — list available strategies
    POST /api/backtest        — run a backtest
    GET  /api/backtest/{id}   — get results by ID

Usage:
    uvicorn backtesting.api:app --port 8000
"""

import datetime as dt
import traceback
import uuid
from typing import Any, Dict, List, Optional

import json

import pandas as pd
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backtesting.data import fetch_backtest_data
from backtesting.engine import BacktestEngine
from backtesting.metrics import compute_metrics
from backtesting.runner import STRATEGIES, _create_strategy, _create_benchmark
from backtesting.db import Base, engine, get_db, init_db, BacktestHistory

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────

# Init DB tables
init_db()

app = FastAPI(
    title="AlphaPilot Backtest API",
    description="Unified backtesting API for ETF rotation and options strategies",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)



# ─────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────
class BacktestRequest(BaseModel):
    strategy: str = Field(..., description="Strategy key (e.g. hydra_v6, pmcc, wheel)")
    years: int = Field(5, ge=1, le=25)
    initial_cash: float = Field(100_000, ge=1000)
    force_refresh: bool = Field(False)


class MetricsResponse(BaseModel):
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    total_trades: Optional[int] = None
    benchmark_total_return: Optional[float] = None
    benchmark_cagr: Optional[float] = None
    benchmark_max_drawdown: Optional[float] = None
    benchmark_sharpe: Optional[float] = None


class TradeRecord(BaseModel):
    date: str
    ticker: str
    action: str
    quantity: int
    price: float
    pnl: float = 0.0
    details: str = ""


class EquityPoint(BaseModel):
    date: str
    value: float


class BacktestResponse(BaseModel):
    id: str
    strategy: str
    strategy_name: str
    years: int
    initial_cash: float
    data_start: str
    data_end: str
    trading_days: int
    metrics: MetricsResponse
    equity_curve: List[EquityPoint]
    benchmark_equity_curve: List[EquityPoint]
    trades: List[TradeRecord]


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/api/strategies")
def list_strategies():
    """List all available strategies with metadata."""
    result = []
    for key, config in STRATEGIES.items():
        result.append({
            "key": key,
            "name": config["name"],
            "ticker": config["ticker"],
            "tickers_needed": config["tickers_needed"],
        })
    return {"strategies": result}


@app.post("/api/backtest", response_model=BacktestResponse)
def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """Run a backtest and return results."""
    if req.strategy not in STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy: {req.strategy}. Available: {list(STRATEGIES.keys())}",
        )

    config = STRATEGIES[req.strategy]
    all_tickers = sorted(set(config["tickers_needed"]))

    try:
        # Fetch data
        data = fetch_backtest_data(
            tickers=all_tickers,
            years=req.years,
            cache_name=f"api_{req.strategy}",
            force_refresh=req.force_refresh,
        )

        # Run strategy
        strategy = _create_strategy(req.strategy)
        engine = BacktestEngine(
            data=data,
            strategy=strategy,
            initial_cash=req.initial_cash,
            iv_scale=config.get("iv_scale", 1.0),
        )
        portfolio = engine.run()
        equity = portfolio.get_equity_curve()

        # Run benchmark
        bench_ticker = config["ticker"]
        bench_strategy = _create_benchmark(bench_ticker)
        bench_engine = BacktestEngine(
            data=data,
            strategy=bench_strategy,
            initial_cash=req.initial_cash,
            iv_scale=config.get("iv_scale", 1.0),
        )
        bench_portfolio = bench_engine.run()
        bench_equity = bench_portfolio.get_equity_curve()

        # Metrics
        avg_rfr = data["RFR"].mean() if "RFR" in data.columns else 0.04
        metrics = compute_metrics(
            equity, trades=portfolio.trades, rfr=avg_rfr, benchmark=bench_equity
        )

        # Build response
        run_id = str(uuid.uuid4())[:8]

        equity_curve = [
            EquityPoint(date=str(d.date() if hasattr(d, "date") else d), value=float(v))
            for d, v in zip(equity.index, equity.values)
        ]
        bench_curve = [
            EquityPoint(date=str(d.date() if hasattr(d, "date") else d), value=float(v))
            for d, v in zip(bench_equity.index, bench_equity.values)
        ]
        trades = [
            TradeRecord(
                date=str(t.date),
                ticker=t.ticker,
                action=t.action,
                quantity=t.quantity,
                price=t.price,
                pnl=t.pnl,
                details=getattr(t, "details", ""),
            )
            for t in portfolio.trades
        ]

        metrics_model = MetricsResponse(**{
            k: v for k, v in metrics.items()
            if k in MetricsResponse.model_fields
        })

        response = BacktestResponse(
            id=run_id,
            strategy=req.strategy,
            strategy_name=config["name"],
            years=req.years,
            initial_cash=req.initial_cash,
            data_start=str(data.index.min().date()),
            data_end=str(data.index.max().date()),
            trading_days=len(data),
            metrics=metrics_model,
            equity_curve=equity_curve,
            benchmark_equity_curve=bench_curve,
            trades=trades,
        )

        # Save to SQLite
        try:
            db_record = BacktestHistory(
                id=run_id,
                strategy=req.strategy,
                strategy_name=config["name"],
                years=req.years,
                initial_cash=req.initial_cash,
                data_start=response.data_start,
                data_end=response.data_end,
                trading_days=response.trading_days,
                total_return=metrics_model.total_return,
                cagr=metrics_model.cagr,
                max_drawdown=metrics_model.max_drawdown,
                sharpe_ratio=metrics_model.sharpe_ratio,
                metrics_json=json.dumps(metrics_model.model_dump()),
                equity_curve_json=json.dumps([e.model_dump() for e in equity_curve]),
                benchmark_curve_json=json.dumps([e.model_dump() for e in bench_curve]),
                trades_json=json.dumps([t.model_dump() for t in trades]),
                created_at=dt.datetime.utcnow()
            )
            db.add(db_record)
            db.commit()
        except Exception as db_err:
            print(f"Failed to save to DB: {db_err}")
            db.rollback()

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}\n{traceback.format_exc()}")


@app.get("/api/backtests")
def list_backtests(limit: int = 50, db: Session = Depends(get_db)):
    """Retrieve history of backtests. Only returns summary data, not full trades/equity."""
    records = db.query(BacktestHistory).order_by(BacktestHistory.created_at.desc()).limit(limit).all()
    results = []
    for r in records:
        results.append({
            "id": r.id,
            "strategy": r.strategy,
            "strategy_name": r.strategy_name,
            "years": r.years,
            "initial_cash": r.initial_cash,
            "data_start": r.data_start,
            "data_end": r.data_end,
            "trading_days": r.trading_days,
            "total_return": r.total_return,
            "cagr": r.cagr,
            "max_drawdown": r.max_drawdown,
            "sharpe_ratio": r.sharpe_ratio,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "metrics": json.loads(r.metrics_json),
        })
    return {"history": results}


@app.get("/api/backtest/{run_id}", response_model=BacktestResponse)
def get_backtest(run_id: str, db: Session = Depends(get_db)):
    """Retrieve a saved backtest result by ID, including complete trade and equity data."""
    record = db.query(BacktestHistory).filter(BacktestHistory.id == run_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
    return BacktestResponse(
        id=record.id,
        strategy=record.strategy,
        strategy_name=record.strategy_name,
        years=record.years,
        initial_cash=record.initial_cash,
        data_start=record.data_start,
        data_end=record.data_end,
        trading_days=record.trading_days,
        metrics=json.loads(record.metrics_json),
        equity_curve=json.loads(record.equity_curve_json),
        benchmark_equity_curve=json.loads(record.benchmark_curve_json),
        trades=json.loads(record.trades_json),
    )


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ─────────────────────────────────────────────────────────
# Static Frontend Serving
# ─────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{catchall:path}")
    def serve_frontend(catchall: str):
        # Serve index.html for root or any unknown non-api paths (React Router support)
        if not catchall.startswith("api/"):
            index_path = os.path.join(FRONTEND_DIR, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Not Found")
else:
    @app.get("/")
    def root():
        return {
            "name": "AlphaPilot Backtest API",
            "version": "1.0.0",
            "docs": "/docs",
            "strategies": f"/api/strategies",
            "note": "Frontend not built. Run 'npm run build' in /frontend to enable the UI."
        }
