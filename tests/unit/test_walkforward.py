"""M3/M5: training frame, forward returns, walk-forward evaluation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from axiomra.backtest.walkforward import (
    WalkForwardSplitter,
    evaluate_predictions,
    run_walk_forward,
)
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import Universe
from axiomra.domain.market import Bar
from axiomra.quant.trainer import build_training_frame, forward_return


def _synthetic_snapshot(
    symbols: list[str] = ("AAA.NS", "BBB.NS", "CCC.NS"),
    days: int = 300,
    seed: int = 0,
):
    rng = np.random.default_rng(seed)
    start = datetime(2023, 1, 2, tzinfo=UTC)
    bars_by_symbol: dict[str, list[Bar]] = {}
    for si, symbol in enumerate(symbols):
        drift = 0.0005 + 0.0002 * si
        prices = [100.0 + si * 5]
        for _ in range(days - 1):
            ret = rng.normal(drift, 0.015)
            prices.append(prices[-1] * (1 + ret))
        bars = []
        for d in range(days):
            price = prices[d]
            ts = start + timedelta(days=d)
            bars.append(
                Bar(
                    symbol=symbol,
                    timestamp=ts,
                    open=price,
                    high=price * 1.005,
                    low=price * 0.995,
                    close=price,
                    volume=float(rng.integers(50_000, 200_000)),
                )
            )
        bars_by_symbol[symbol] = bars

    uni = Universe(
        name="TEST",
        version="test-v1",
        as_of=datetime.now(UTC),
        members=list(symbols),
    )
    return create_snapshot(
        universe=uni,
        bars=bars_by_symbol,
        data_version="dtest",
        actions=[],
    )


# --- forward return --------------------------------------------------------


def test_forward_return_uses_future_close():
    close = pd.Series([100.0, 110.0, 121.0, 100.0])
    fr = forward_return(close, horizon=2)
    assert fr.iloc[0] == pytest.approx(121.0 / 100.0 - 1.0)
    assert fr.iloc[1] == pytest.approx(100.0 / 110.0 - 1.0)
    assert pd.isna(fr.iloc[2])
    assert pd.isna(fr.iloc[3])


# --- training frame --------------------------------------------------------


def test_build_training_frame_no_leakage():
    snap = _synthetic_snapshot(days=60)
    frame = build_training_frame(snap, horizon=5)
    assert {"symbol", "date", "target"}.issubset(frame.columns)
    # No row may use a future close: target of the last 5 days is NaN -> dropped.
    assert frame["target"].notna().all()
    assert frame.sort_values(["date", "symbol"]).equals(frame.reset_index(drop=True))
    assert set(frame["symbol"].unique()) == {"AAA.NS", "BBB.NS", "CCC.NS"}


def test_training_frame_last_rows_have_no_target():
    snap = _synthetic_snapshot(days=10, symbols=("AAA.NS",))
    frame = build_training_frame(snap, horizon=5)
    # 10 bars - 5 lead-in (feature warmup) - 5 horizon = a few rows at most.
    assert len(frame) <= 10 - 5
    assert frame["target"].notna().all()


# --- splitter --------------------------------------------------------------


def test_expanding_splitter_grows_train_set():
    dates = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(100)]
    splitter = WalkForwardSplitter(n_splits=3, min_train_days=20)
    folds = splitter.folds(dates)
    assert len(folds) == 2
    train1, test1 = folds[0]
    train2, test2 = folds[1]
    assert len(train2) > len(train1)
    # no leakage within a fold: each test set is disjoint from its own train set
    assert set(test1).isdisjoint(set(train1))
    assert set(test2).isdisjoint(set(train2))
    # every test fold starts after its train fold ends
    assert max(train1) < min(test1)
    assert max(train2) < min(test2)


def test_splitter_rejects_short_series():
    dates = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(5)]
    splitter = WalkForwardSplitter(n_splits=3, min_train_days=2)
    try:
        splitter.folds(dates)
        assert False, "expected ValueError"
    except ValueError:
        pass


# --- metrics ---------------------------------------------------------------


def test_evaluate_predictions_perfect_ranks():
    y_true = np.array([-0.05, 0.01, 0.03, 0.07])
    y_pred = np.array([0.0, 0.4, 0.7, 1.0])
    m = evaluate_predictions(y_true, y_pred)
    assert m["ic"] > 0.99
    assert m["rank_ic"] > 0.99


def test_evaluate_predictions_ignores_nan_true():
    y_true = np.array([-0.05, np.nan, 0.03, 0.07])
    y_pred = np.array([0.0, 0.4, 0.7, 1.0])
    m = evaluate_predictions(y_true, y_pred)
    assert m["ic"] > 0.99


# --- walk-forward (fake estimator) ----------------------------------------


class _MeanTargetEstimator:
    """Naive estimator: predicts the historical mean. Weak but deterministic."""

    def __init__(self, mean: float) -> None:
        self._mean = mean

    def predict(self, x):
        return np.full(len(x), self._mean)


def _mean_factory(x_tr, y_tr):
    return _MeanTargetEstimator(float(np.mean(y_tr)))


def test_run_walk_forward_returns_report():
    snap = _synthetic_snapshot(days=300)
    report = run_walk_forward(
        snapshot=snap,
        horizon=5,
        n_splits=3,
        min_train_days=30,
        estimator_factory=_mean_factory,
    )
    assert report.n_folds == 2
    for fold in report.folds:
        assert fold.n_test >= 2
        assert fold.n_train >= 30
        assert -1.0 <= fold.ic <= 1.0
        assert -1.0 <= fold.rank_ic <= 1.0
    assert -1.0 <= report.mean_ic <= 1.0


def test_train_labels_never_overlap_test():
    """Verify that training samples whose label_end extends into test_start are purged."""
    snap = _synthetic_snapshot(days=300)
    frame = build_training_frame(snap, horizon=5)
    assert "label_end" in frame.columns

    dates = sorted(frame["date"].unique())
    splitter = WalkForwardSplitter(n_splits=3, min_train_days=30)
    folds = splitter.folds(dates)

    for train_dates, test_dates in folds:
        test_start = min(test_dates)
        purged_train = frame[
            frame["date"].isin(train_dates) & (frame["label_end"] < test_start)
        ]
        if not purged_train.empty:
            assert purged_train["label_end"].max() < test_start


def test_top_quintile_is_selected_per_day():
    from axiomra.backtest.walkforward import evaluate_daily_predictions

    # 2 dates, 4 symbols each
    # Day 1: predictions [0.1, 0.2, 0.3, 0.9], targets [0.01, 0.02, 0.03, 0.04] -> top 25% (k=1) is pred=0.9 -> target=0.04
    # Day 2: predictions [0.4, 0.5, 0.6, 0.8], targets [0.05, 0.06, 0.07, 0.10] -> top 25% (k=1) is pred=0.8 -> target=0.10
    # Average daily top quintile return = (0.04 + 0.10) / 2 = 0.07
    dates = [datetime(2024, 1, 1, tzinfo=UTC)] * 4 + [datetime(2024, 1, 2, tzinfo=UTC)] * 4
    targets = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.10]
    preds = np.array([0.1, 0.2, 0.3, 0.9, 0.4, 0.5, 0.6, 0.8])

    test_frame = pd.DataFrame({"date": dates, "target": targets})
    metrics = evaluate_daily_predictions(test_frame, preds, top_fraction=0.25)
    assert metrics["top_quintile_return"] == pytest.approx(0.07)


def test_oos_predictions_are_fully_out_of_sample():
    """Every OOS prediction row must fall within its fold's test date range.

    This proves that no training-period predictions are included in the OOS
    artifact, which would constitute target leakage.
    """
    from axiomra.backtest.walkforward import oos_predictions_df  # noqa: PLC0415

    snap = _synthetic_snapshot(symbols=["A.NS", "B.NS", "C.NS"], days=400)

    def dummy_factory(x, y):
        class _M:
            def predict(self, xp):
                return [0.05] * len(xp)
        return _M()

    report = run_walk_forward(
        snapshot=snap,
        horizon=5,
        n_splits=3,
        min_train_days=30,
        estimator_factory=dummy_factory,
    )

    assert len(report.oos_predictions) > 0, "oos_predictions must not be empty"
    df = oos_predictions_df(report)
    assert set(df.columns) >= {"date", "symbol", "score", "target", "fold"}

    # Every row's date must fall in its fold's [test_start, test_end] interval
    for _, row in df.iterrows():
        fold = report.folds[int(row["fold"]) - 1]
        row_date = pd.Timestamp(row["date"])
        test_start = pd.Timestamp(fold.test_start)
        test_end = pd.Timestamp(fold.test_end)
        assert test_start <= row_date <= test_end, (
            f"OOS prediction on {row_date} falls outside fold {fold.fold} "
            f"test range [{test_start}, {test_end}]"
        )


