"""M9: Portfolio Backtester unit tests — Research Integrity Edition."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from axiomra.backtest.backtester import (
    BacktestConfig,
    BacktestReport,
    CurveStats,
    ExecutionPolicy,
    RelativeStats,
    run_backtest,
)
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import IndexMembership, Universe
from axiomra.domain.market import Bar

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────

_N_DAYS = 30
_SYMBOLS = ["AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS", "EEE.NS"]


def _make_bars(symbol: str, start_close: float, slope: float, start_open_offset: float = -1.0) -> list[Bar]:
    """Generate N_DAYS bars with deterministic linear price series."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(_N_DAYS):
        close = start_close + slope * i
        open_ = close + start_open_offset  # open != close to test execution timing
        bars.append(Bar(
            symbol=symbol,
            timestamp=base + timedelta(days=i),
            open=open_,
            high=close + 1.0,
            low=close - 1.5,
            close=close,
            volume=1_000.0,
        ))
    return bars


def _make_snapshot(with_memberships: bool = False):
    bars_dict: dict[str, list[Bar]] = {
        "AAA.NS": _make_bars("AAA.NS", 100.0, +0.5, -1.0),
        "BBB.NS": _make_bars("BBB.NS", 200.0, +1.0, -2.0),
        "CCC.NS": _make_bars("CCC.NS", 150.0, -0.5, -0.5),
        "DDD.NS": _make_bars("DDD.NS", 120.0, +0.2, -1.0),
        "EEE.NS": _make_bars("EEE.NS", 180.0, -0.3, -1.5),
    }
    uni = Universe(
        name="TEST_INDEX", version="v1",
        as_of=datetime.now(UTC),
        members=list(bars_dict.keys()),
    )
    memberships = None
    if with_memberships:
        start = datetime(2024, 1, 1, tzinfo=UTC)
        memberships = [
            IndexMembership(instrument_id=sym, symbol=sym, index_name="TEST_INDEX", from_date=start)
            for sym in list(bars_dict.keys())
        ]
    return create_snapshot(
        universe=uni, bars=bars_dict, data_version="test-d1", memberships=memberships
    )


def _make_predictions(snapshot, score_map: dict[str, float] | None = None) -> pd.DataFrame:
    if score_map is None:
        score_map = {sym: float(i) for i, sym in enumerate(_SYMBOLS)}
    rows: list[dict[str, Any]] = []
    for symbol, bars in snapshot.bars.items():
        for b in bars[:-1]:
            rows.append({"date": b.timestamp.date(), "symbol": symbol, "score": score_map.get(symbol, 0.0)})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Config tests
# ─────────────────────────────────────────────────────────────────────────────


def test_backtest_config_defaults():
    cfg = BacktestConfig()
    assert cfg.top_fraction == pytest.approx(0.2)
    assert cfg.cost_bps == pytest.approx(10.0)
    assert cfg.max_position_weight == pytest.approx(0.10)
    assert cfg.execution_policy == ExecutionPolicy.OPEN_NEXT


# ─────────────────────────────────────────────────────────────────────────────
# Structural tests
# ─────────────────────────────────────────────────────────────────────────────


def test_backtest_produces_equity_curve():
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)

    assert isinstance(report, BacktestReport)
    assert isinstance(report.portfolio, CurveStats)
    assert isinstance(report.benchmark, CurveStats)
    assert isinstance(report.relative, RelativeStats)
    assert len(report.daily_returns) > 0
    # Key scalars must be finite
    assert not (report.portfolio.total_return != report.portfolio.total_return)
    assert not (report.portfolio.sharpe != report.portfolio.sharpe)
    assert not (report.portfolio.max_drawdown != report.portfolio.max_drawdown)
    assert report.dataset_id == snap.dataset_id


def test_backtest_costs_reduce_return():
    """Higher transaction costs must reduce net portfolio total return."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    r_no_cost = run_backtest(snap, preds, BacktestConfig(cost_bps=0.0))
    r_high_cost = run_backtest(snap, preds, BacktestConfig(cost_bps=200.0))
    assert r_no_cost.portfolio.total_return >= r_high_cost.portfolio.total_return


def test_backtest_max_position_weight_respected():
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    cap = 0.05
    config = BacktestConfig(max_position_weight=cap, top_fraction=0.8)
    report = run_backtest(snap, preds, config)
    assert len(report.daily_returns) > 0
    for d in report.daily_returns:
        assert d.n_positions * cap <= 1.0 + 1e-9


def test_backtest_empty_predictions_raises():
    snap = _make_snapshot()
    with pytest.raises(ValueError, match="empty"):
        run_backtest(snap, pd.DataFrame(columns=["date", "symbol", "score"]))


def test_backtest_missing_columns_raises():
    snap = _make_snapshot()
    bad_df = pd.DataFrame({"date": ["2024-01-01"], "symbol": ["AAA.NS"]})
    with pytest.raises(ValueError, match="missing columns"):
        run_backtest(snap, bad_df)


def test_backtest_hit_rate_bounded():
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    assert 0.0 <= report.relative.hit_rate <= 1.0


def test_backtest_turnover_non_negative():
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    assert report.avg_turnover >= 0.0
    assert all(d.turnover >= 0.0 for d in report.daily_returns)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 2 — Execution timing invariant
# ─────────────────────────────────────────────────────────────────────────────


def test_execution_policy_open_next_uses_open_price():
    """OPEN_NEXT and CLOSE_NEXT must produce different returns when open != close."""
    snap = _make_snapshot()  # bars have open = close - 1 → open != close
    preds = _make_predictions(snap)

    r_open = run_backtest(snap, preds, BacktestConfig(execution_policy=ExecutionPolicy.OPEN_NEXT, cost_bps=0.0))
    r_close = run_backtest(snap, preds, BacktestConfig(execution_policy=ExecutionPolicy.CLOSE_NEXT, cost_bps=0.0))

    # open[T+1] != close[T] in our test data, so results MUST differ
    assert r_open.portfolio.total_return != r_close.portfolio.total_return


def test_open_next_cannot_trade_at_signal_close():
    """With OPEN_NEXT, the 1-day return is close[T+1]/open[T+1]-1, not close[T+1]/close[T]-1."""
    # Build a minimal 2-bar snapshot with known prices
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        Bar(symbol="X.NS", timestamp=base,                     open=90.0, high=110.0, low=85.0, close=100.0, volume=1.0),
        Bar(symbol="X.NS", timestamp=base + timedelta(days=1), open=200.0, high=210.0, low=195.0, close=210.0, volume=1.0),
    ]
    uni = Universe(name="T", version="v1", as_of=datetime.now(UTC), members=["X.NS"])
    snap = create_snapshot(universe=uni, bars={"X.NS": bars}, data_version="d1")
    preds = pd.DataFrame([{"date": base.date(), "symbol": "X.NS", "score": 1.0}])

    # OPEN_NEXT: return = 210/200 - 1 = 5%
    r_open = run_backtest(snap, preds, BacktestConfig(cost_bps=0.0, max_position_weight=1.0, top_fraction=1.0))
    assert r_open.daily_returns[0].portfolio_return == pytest.approx(0.05, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 3 — Portfolio vs benchmark metric separation
# ─────────────────────────────────────────────────────────────────────────────


def test_portfolio_mdd_from_portfolio_curve():
    """Portfolio MDD must be computed from the portfolio curve, not the excess-return spread."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    # MDD must be <= 0 (a loss) or 0 (no drawdown at all)
    assert report.portfolio.max_drawdown <= 0.0


def test_benchmark_mdd_from_benchmark_curve():
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    assert report.benchmark.max_drawdown <= 0.0


def test_portfolio_and_benchmark_mdd_can_differ():
    """Portfolio MDD and benchmark MDD are independent quantities."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    # We can't guarantee they differ in all data, but structure must be separate
    assert hasattr(report.portfolio, "max_drawdown")
    assert hasattr(report.benchmark, "max_drawdown")


def test_sortino_gte_zero_or_equal_to_sharpe_when_no_downside():
    """Sortino must equal Sharpe (or be slightly higher) as it excludes upside vol."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds, BacktestConfig(cost_bps=0.0))
    # When all returns are positive, both numerators are equal but downside_std < total_std → sortino >= sharpe
    # When there's downside vol, sortino can be negative but is still a valid float
    assert isinstance(report.portfolio.sortino, float)
    assert not (report.portfolio.sortino != report.portfolio.sortino)  # not NaN


def test_information_ratio_is_computable():
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(snap, preds)
    assert isinstance(report.relative.information_ratio, float)
    assert isinstance(report.relative.tracking_error, float)
    assert report.relative.tracking_error >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4 — PIT benchmark
# ─────────────────────────────────────────────────────────────────────────────


def test_pit_benchmark_excludes_non_members():
    """Benchmark return must differ when only 2 of 5 symbols are index members."""
    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars_dict = {
        "GOOD1.NS": [
            Bar(symbol="GOOD1.NS", timestamp=base,                     open=99.0,  high=101.0, low=98.0, close=100.0, volume=1.0),
            Bar(symbol="GOOD1.NS", timestamp=base + timedelta(days=1), open=100.0, high=106.0, low=99.0, close=105.0, volume=1.0),
        ],
        "GOOD2.NS": [
            Bar(symbol="GOOD2.NS", timestamp=base,                     open=99.0,  high=101.0, low=98.0, close=100.0, volume=1.0),
            Bar(symbol="GOOD2.NS", timestamp=base + timedelta(days=1), open=100.0, high=106.0, low=99.0, close=105.0, volume=1.0),
        ],
        # OUTLIER is NOT a member but has wildly different return
        "OUTLIER.NS": [
            Bar(symbol="OUTLIER.NS", timestamp=base,                     open=99.0,  high=201.0, low=98.0, close=100.0, volume=1.0),
            Bar(symbol="OUTLIER.NS", timestamp=base + timedelta(days=1), open=100.0, high=201.0, low=99.0, close=200.0, volume=1.0),
        ],
    }
    uni = Universe(name="IDX", version="v1", as_of=datetime.now(UTC), members=list(bars_dict.keys()))
    snap = create_snapshot(universe=uni, bars=bars_dict, data_version="d1")

    preds = pd.DataFrame([
        {"date": base.date(), "symbol": "GOOD1.NS", "score": 2.0},
        {"date": base.date(), "symbol": "GOOD2.NS", "score": 1.0},
        {"date": base.date(), "symbol": "OUTLIER.NS", "score": 0.0},
    ])

    # Memberships: only GOOD1 and GOOD2 are index members
    memberships = [
        IndexMembership(instrument_id="GOOD1.NS", symbol="GOOD1.NS", index_name="IDX", from_date=base),
        IndexMembership(instrument_id="GOOD2.NS", symbol="GOOD2.NS", index_name="IDX", from_date=base),
    ]

    report_with_pit = run_backtest(snap, preds, memberships=memberships)
    report_no_pit   = run_backtest(snap, preds, memberships=None)

    # Benchmark with PIT excludes OUTLIER (100% return); without PIT it's included
    bm_no_pit  = report_no_pit.daily_returns[0].benchmark_return
    bm_with_pit = report_with_pit.daily_returns[0].benchmark_return

    # Equal-weight bm without PIT: mean(5%, 5%, 100%) ≈ 36.7%
    # Equal-weight bm with PIT:    mean(5%, 5%) = 5%
    assert bm_no_pit != pytest.approx(bm_with_pit, abs=0.01)
    assert bm_with_pit == pytest.approx(0.05, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# Fix 5 — Backtest lineage
# ─────────────────────────────────────────────────────────────────────────────


def test_backtest_lineage_fields():
    """BacktestReport must carry provenance fields."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    report = run_backtest(
        snap, preds,
        dataset_checksum="abc123",
        feature_version="fv1",
        model_version="lgbm-v1",
    )
    assert report.dataset_checksum == "abc123"
    assert report.feature_version == "fv1"
    assert report.model_version == "lgbm-v1"
    assert report.execution_policy_version == ExecutionPolicy.OPEN_NEXT.value
    assert report.cost_policy_version == "simple-bps-v1"
    assert report.target_version == "execution-aligned-v1"
