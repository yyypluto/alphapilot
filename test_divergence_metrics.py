import pandas as pd

from utils import calculate_divergence_metrics


def _make_df(values, start="2026-01-01"):
    idx = pd.date_range(start=start, periods=len(values), freq="D")
    return pd.DataFrame({"Close": values}, index=idx)


def test_severe_divergence_signal():
    # QQQ near recent high: drawdown about -1%
    qqq = _make_df([100] * 59 + [99])

    # SOXX lagging: rolling max 100, current 92 => -8%
    soxx = _make_df([100] * 59 + [92])

    out = calculate_divergence_metrics(qqq, soxx, window=60)
    assert not out.empty
    assert out.iloc[-1]["Divergence_Signal"] == "🔴 严重背离"


def test_mild_divergence_signal():
    # QQQ near recent high: -1%
    qqq = _make_df([100] * 59 + [99])

    # SOXX lagging: -5%
    soxx = _make_df([100] * 59 + [95])

    out = calculate_divergence_metrics(qqq, soxx, window=60)
    assert out.iloc[-1]["Divergence_Signal"] == "🟠 轻微背离"


def test_healthy_trend_signal():
    qqq = _make_df([100] * 60)
    soxx = _make_df([100] * 60)

    out = calculate_divergence_metrics(qqq, soxx, window=60)
    assert out.iloc[-1]["Divergence_Signal"] == "🟢 趋势健康"
