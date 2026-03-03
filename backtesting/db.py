"""
Database configuration and models for the unified backtest history.
"""

from datetime import datetime
import json
import os
from pathlib import Path

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# ─────────────────────────────────────────────────────────
# Connection Setup
# ─────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{DATA_DIR}/backtest_history.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────

class BacktestHistory(Base):
    """
    Stores comprehensive results of a backtest run.
    Instead of complex relational tables for daily equity/trades (which is slow
    and unnecessary for static historical records), we store them as JSON text fields.
    """
    __tablename__ = "backtest_history"

    id = Column(String, primary_key=True, index=True)  # UUID string
    strategy = Column(String, index=True, nullable=False)
    strategy_name = Column(String, nullable=False)
    
    # Parameters
    years = Column(Integer, nullable=False)
    initial_cash = Column(Float, nullable=False)
    
    # Ranges
    data_start = Column(String, nullable=False)
    data_end = Column(String, nullable=False)
    trading_days = Column(Integer, nullable=False)
    
    # Key Metrics (broken out for sorting/filtering)
    total_return = Column(Float)
    cagr = Column(Float)
    max_drawdown = Column(Float)
    sharpe_ratio = Column(Float)
    
    # Full records (JSON serialized)
    metrics_json = Column(Text, nullable=False)
    equity_curve_json = Column(Text, nullable=False)
    benchmark_curve_json = Column(Text, nullable=False)
    trades_json = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency injector for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
