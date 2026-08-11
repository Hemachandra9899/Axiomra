"""Unit tests for end-to-end instrument_id propagation and joining across the pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from axiomra.backtest.backtester import run_backtest
from axiomra.backtest.walkforward import oos_predictions_df, run_walk_forward
from axiomra.data.instruments import Instrument, InstrumentMaster
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import Universe
from axiomra.domain.market import Bar
from axiomra.quant.trainer import build_training_frame


def test_build_training_frame_includes_instrument_id():
    """build_training_frame must include instrument_id column resolved from InstrumentMaster."""
    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-101",
            symbol="RELIANCE.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        Bar(
            symbol="RELIANCE.NS",
            timestamp=base + timedelta(days=i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000.0,
        )
        for i in range(60)
    ]
    uni = Universe(name="TEST", version="v1", as_of=datetime.now(UTC), members=["RELIANCE.NS"])
    snap = create_snapshot(universe=uni, bars={"RELIANCE.NS": bars}, data_version="d1")

    frame = build_training_frame(snap, instruments=master)

    assert not frame.empty
    assert "instrument_id" in frame.columns
    assert (frame["instrument_id"] == "INST-101").all()


def test_walkforward_oos_predictions_contain_instrument_id():
    """run_walk_forward OOS prediction rows must include instrument_id and model_version."""
    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-777",
            symbol="AAA.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    base = datetime(2020, 1, 1, tzinfo=UTC)
    bars = [
        Bar(
            symbol="AAA.NS",
            timestamp=base + timedelta(days=i),
            open=100.0 + i * 0.1,
            high=101.0 + i * 0.1,
            low=99.0 + i * 0.1,
            close=100.0 + i * 0.1,
            volume=10000.0,
        )
        for i in range(300)
    ]
    uni = Universe(name="TEST", version="v1", as_of=datetime.now(UTC), members=["AAA.NS"])
    snap = create_snapshot(universe=uni, bars={"AAA.NS": bars}, data_version="d1")

    def dummy_factory(x_tr, y_tr):
        class _M:
            def predict(self, x):
                return [0.05] * len(x)
        return _M()

    report = run_walk_forward(
        snapshot=snap,
        horizon=5,
        n_splits=3,
        min_train_days=30,
        estimator_factory=dummy_factory,
        instruments=master,
    )

    df_oos = oos_predictions_df(report)
    assert not df_oos.empty
    assert "instrument_id" in df_oos.columns
    assert "model_version" in df_oos.columns
    assert (df_oos["instrument_id"] == "INST-777").all()


def test_backtest_joins_on_instrument_id():
    """run_backtest must join return matrix and predictions_df on (instrument_id, date)."""
    master = InstrumentMaster()
    master.upsert(
        Instrument(
            instrument_id="INST-999",
            symbol="XYZ.NS",
            active_from=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )

    base = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        Bar(symbol="XYZ.NS", timestamp=base, open=100.0, high=105.0, low=99.0, close=102.0, volume=1000.0),
        Bar(symbol="XYZ.NS", timestamp=base + timedelta(days=1), open=102.0, high=108.0, low=101.0, close=106.0, volume=1000.0),
    ]
    uni = Universe(name="TEST", version="v1", as_of=datetime.now(UTC), members=["XYZ.NS"])
    snap = create_snapshot(universe=uni, bars={"XYZ.NS": bars}, data_version="d1")

    # predictions_df carries instrument_id
    preds = pd.DataFrame([
        {
            "date": base.date(),
            "instrument_id": "INST-999",
            "symbol": "XYZ.NS",
            "score": 1.0,
        }
    ])

    report = run_backtest(snap, preds, instruments=master)
    assert len(report.daily_returns) == 1
    assert report.daily_returns[0].n_positions == 1
