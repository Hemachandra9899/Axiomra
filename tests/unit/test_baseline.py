"""M10: Trusted Baseline Report unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from axiomra.backtest.backtester import BacktestConfig, run_backtest
from axiomra.backtest.walkforward import FoldReport, WalkForwardReport
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import Universe
from axiomra.domain.market import Bar
from axiomra.research.baseline import (
    BaselineReport,
    CompareResult,
    create_baseline,
    load_baseline,
    save_baseline,
)
from axiomra.storage.local import LocalArtifactStore

# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

_N_DAYS = 30
_SYMBOLS = ["AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS", "EEE.NS"]


def _make_bars(symbol: str, start: float = 100.0, slope: float = 0.5) -> list[Bar]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(
            symbol=symbol,
            timestamp=base + timedelta(days=i),
            open=start + slope * i - 0.5,
            high=start + slope * i + 1.0,
            low=start + slope * i - 1.0,
            close=start + slope * i,
            volume=1_000.0,
        )
        for i in range(_N_DAYS)
    ]


def _make_snapshot():
    bars_dict = {sym: _make_bars(sym, 100.0 + 10 * k, 0.3 * k) for k, sym in enumerate(_SYMBOLS)}
    uni = Universe(name="TEST", version="v1", as_of=datetime.now(UTC), members=list(bars_dict.keys()))
    return create_snapshot(universe=uni, bars=bars_dict, data_version="test-d1")


def _make_predictions(snapshot) -> pd.DataFrame:
    rows = []
    for i, (symbol, bars) in enumerate(snapshot.bars.items()):
        for b in bars[:-1]:
            rows.append({"date": b.timestamp.date(), "symbol": symbol, "score": float(i)})
    return pd.DataFrame(rows)


def _make_wf_report(mean_ic: float = 0.05) -> WalkForwardReport:
    base_dt = datetime(2024, 1, 1, tzinfo=UTC)
    fold = FoldReport(
        fold=1,
        train_start=base_dt,
        test_start=base_dt + timedelta(days=200),
        test_end=base_dt + timedelta(days=250),
        n_train=1000,
        n_test=500,
        ic=mean_ic,
        rank_ic=mean_ic * 0.9,
        ic_ir=mean_ic * 5.0,
        pct_positive_ic=0.6,
        hit_rate=0.55,
        top_quintile_return=mean_ic * 2.0,
    )
    return WalkForwardReport(
        folds=[fold],
        mean_ic=mean_ic,
        mean_rank_ic=mean_ic * 0.9,
        mean_ic_ir=mean_ic * 5.0,
        mean_pct_positive_ic=0.6,
        mean_hit_rate=0.55,
        mean_top_quintile_return=mean_ic * 2.0,
    )


def _make_full_baseline(tmp_path, model_version: str = "lgbm-v1", mean_ic: float = 0.05) -> BaselineReport:
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    bt_report = run_backtest(snap, preds, BacktestConfig(cost_bps=10.0))
    wf_report = _make_wf_report(mean_ic=mean_ic)
    return create_baseline(
        model_version=model_version,
        dataset_id=snap.dataset_id,
        dataset_checksum=snap.checksum,
        walk_forward_report=wf_report,
        backtest_report=bt_report,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_baseline_round_trip(tmp_path):
    """save_baseline → load_baseline must restore an identical struct."""
    store = LocalArtifactStore(root_dir=tmp_path / "artifacts")
    baseline = _make_full_baseline(tmp_path)

    key = save_baseline(baseline, store=store)
    assert store.exists(key)

    restored = load_baseline(baseline.model_version, baseline.dataset_id, store=store)
    assert restored.model_version == baseline.model_version
    assert restored.dataset_id == baseline.dataset_id
    assert restored.dataset_checksum == baseline.dataset_checksum
    assert restored.mean_ic == pytest.approx(baseline.mean_ic, abs=1e-9)
    assert restored.sharpe == pytest.approx(baseline.sharpe, abs=1e-9)
    assert restored.max_drawdown == pytest.approx(baseline.max_drawdown, abs=1e-9)


def test_baseline_checksum_links_dataset(tmp_path):
    """BaselineReport must carry the exact dataset_checksum of the source snapshot."""
    snap = _make_snapshot()
    preds = _make_predictions(snap)
    bt_report = run_backtest(snap, preds)
    wf_report = _make_wf_report()

    baseline = create_baseline(
        model_version="lgbm-v1",
        dataset_id=snap.dataset_id,
        dataset_checksum=snap.checksum,
        walk_forward_report=wf_report,
        backtest_report=bt_report,
    )
    assert baseline.dataset_checksum == snap.checksum
    assert baseline.dataset_id == snap.dataset_id


def test_baseline_compare_no_regression():
    """compare() must report no regression when the candidate is identical."""
    baseline = _make_full_baseline(None)
    # Candidate with same IC
    candidate = _make_full_baseline(None, model_version="lgbm-v2", mean_ic=0.05)
    result = baseline.compare(candidate)
    assert isinstance(result, CompareResult)
    assert not result.any_regression


def test_baseline_compare_detects_ic_regression():
    """compare() must flag regression when mean_ic drops by > 5%."""
    baseline = _make_full_baseline(None, mean_ic=0.10)
    # Drop IC by 50% — clearly a regression
    candidate = _make_full_baseline(None, model_version="lgbm-bad", mean_ic=0.04)
    result = baseline.compare(candidate)
    assert result.any_regression
    ic_delta = next(d for d in result.deltas if d.metric == "mean_ic")
    assert ic_delta.regressed
    assert ic_delta.pct_change < -0.05


def test_baseline_compare_improvement_not_flagged():
    """compare() must NOT flag regression when candidate improves all metrics."""
    baseline = _make_full_baseline(None, mean_ic=0.03)
    candidate = _make_full_baseline(None, model_version="lgbm-better", mean_ic=0.08)
    result = baseline.compare(candidate)
    # IC improved; no regression expected there
    ic_delta = next(d for d in result.deltas if d.metric == "mean_ic")
    assert not ic_delta.regressed


def test_baseline_load_missing_raises(tmp_path):
    """load_baseline must raise FileNotFoundError when artifact doesn't exist."""
    store = LocalArtifactStore(root_dir=tmp_path / "artifacts")
    with pytest.raises(FileNotFoundError):
        load_baseline("nonexistent-model", "ds-doesnotexist", store=store)


def test_baseline_created_at_utc():
    """created_at on the baseline must be timezone-aware UTC."""
    baseline = _make_full_baseline(None)
    assert baseline.created_at.tzinfo is not None


def test_baseline_summary_mirrors_reports():
    """Summary scalar fields must echo the underlying report values."""
    baseline = _make_full_baseline(None, mean_ic=0.07)
    assert baseline.mean_ic == pytest.approx(baseline.walk_forward_report.mean_ic, abs=1e-9)
    assert baseline.sharpe == pytest.approx(baseline.backtest_report.sharpe, abs=1e-9)
    assert baseline.max_drawdown == pytest.approx(baseline.backtest_report.max_drawdown, abs=1e-9)
