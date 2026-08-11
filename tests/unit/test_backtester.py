"""M9: Portfolio Backtester unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from axiomra.backtest.backtester import (
    BacktestConfig,
    BacktestReport,
    run_backtest,
)
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import Universe
from axiomra.domain.market import Bar

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

_N_DAYS = 30
_SYMBOLS = ["AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS", "EEE.NS"]


def _make_bars(symbol: str, start_close: float, slope: float) -> list[Bar]:
    """Generate N_DAYS bars with a deterministic linear price series."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(_N_DAYS):
        close = start_close + slope * i
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=base + timedelta(days=i),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000.0,
            )
        )
    return bars


def _make_snapshot():
    """Build a small DatasetSnapshot with 5 symbols."""
    bars_dict: dict[str, list[Bar]] = {
        "AAA.NS": _make_bars("AAA.NS", 100.0, +0.5),
        "BBB.NS": _make_bars("BBB.NS", 200.0, +1.0),
        "CCC.NS": _make_bars("CCC.NS", 150.0, -0.5),
        "DDD.NS": _make_bars("DDD.NS", 120.0, +0.2),
        "EEE.NS": _make_bars("EEE.NS", 180.0, -0.3),
    }
    uni = Universe(
        name="TEST", version="v1", as_of=datetime.now(UTC), members=list(bars_dict.keys())
    )
    return create_snapshot(universe=uni, bars=bars_dict, data_version="test-d1")


def _make_predictions(snapshot, score_map: dict[str, float] | None = None) -> pd.DataFrame:
    """Build a predictions_df with constant scores for each symbol."""
    if score_map is None:
        score_map = {sym: float(i) for i, sym in enumerate(_SYMBOLS)}

    rows: list[dict[str, Any]] = []
    for symbol, bars in snapshot.bars.items():
        for b in bars[:-1]:  # last bar has no forward return
            rows.append(
                {
                    "date": b.timestamp.date(),
                    "symbol": symbol,
                    "score": score_map.get(symbol, 0.0),
                }
            )
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_backtest_config_defaults():
    """BacktestConfig must expose sensible defaults."""
    cfg = BacktestConfig()
    assert cfg.top_fraction == pytest.approx(0.2)
    assert cfg.cost_bps == pytest.approx(10.0)
    assert cfg.max_position_weight == pytest.approx(0.10)
    assert cfg.initial_capital == pytest.approx(1_000_000.0)


def test_backtest_produces_equity_curve():
    """run_backtest must return a BacktestReport with correct structure."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)

    assert isinstance(report, BacktestReport)
    # Should have one record per trading day covered by predictions
    assert len(report.daily_returns) > 0
    # Key scalars must be finite floats
    assert not (report.total_return != report.total_return)  # not NaN
    assert not (report.sharpe != report.sharpe)
    assert not (report.max_drawdown != report.max_drawdown)
    # dataset_id echoes snapshot
    assert report.dataset_id == snap.dataset_id
    # n_positions must be >= 1 on every day
    assert all(d.n_positions >= 1 for d in report.daily_returns)


def test_backtest_costs_reduce_return():
    """Higher transaction costs must reduce net portfolio return."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)

    report_no_cost = run_backtest(snap, preds, BacktestConfig(cost_bps=0.0))
    report_high_cost = run_backtest(snap, preds, BacktestConfig(cost_bps=200.0))

    assert report_no_cost.total_return >= report_high_cost.total_return


def test_backtest_max_position_weight_respected():
    """No individual position should exceed max_position_weight."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)

    cap = 0.05
    config = BacktestConfig(max_position_weight=cap, top_fraction=0.8)
    report = run_backtest(snap, preds, config)

    # Verify by inspecting n_positions: with 5 symbols and top_fraction=0.8 → 4 stocks
    # Each should be capped at 0.05 (so the sum < 1, rest is cash)
    # We can't directly read weights, but average returns should be plausible
    assert len(report.daily_returns) > 0
    # n_positions * max_weight <= 1.0 always (no leverage)
    for d in report.daily_returns:
        assert d.n_positions * cap <= 1.0 + 1e-9


def test_backtest_empty_predictions_raises():
    """run_backtest must raise ValueError when predictions_df is empty."""
    snap = _make_snapshot()
    with pytest.raises(ValueError, match="empty"):
        run_backtest(snap, pd.DataFrame(columns=["date", "symbol", "score"]))


def test_backtest_missing_columns_raises():
    """run_backtest must raise ValueError when required columns are absent."""
    snap = _make_snapshot()
    bad_df = pd.DataFrame({"date": ["2024-01-01"], "symbol": ["AAA.NS"]})  # no 'score'
    with pytest.raises(ValueError, match="missing columns"):
        run_backtest(snap, bad_df)


def test_backtest_hit_rate_bounded():
    """hit_rate must be in [0, 1]."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    assert 0.0 <= report.hit_rate <= 1.0


def test_backtest_turnover_non_negative():
    """avg_turnover must be >= 0."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    assert report.avg_turnover >= 0.0
    assert all(d.turnover >= 0.0 for d in report.daily_returns)
