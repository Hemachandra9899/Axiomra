"""Feature pipeline: point-in-time safety and NaN behaviour."""

from __future__ import annotations

import pandas as pd
import pytest

from axiomra.features.pipeline import FEATURE_VERSION, calculate_features
from tests.conftest import make_ohlcv


def test_features_do_not_leak_future():
    df = make_ohlcv()
    out = calculate_features(df)

    assert out.loc[out.index[0], "ret_1d"] != out.loc[out.index[1], "ret_1d"]
    assert pd.isna(out["momentum_20d"].iloc[0])

    # momentum_20d at t must equal pct_change(20) of close, computed at t only.
    expected = df["close"].pct_change(20)
    pd.testing.assert_series_equal(
        out["momentum_20d"], expected, check_names=False
    )


def test_features_never_use_future_rows():
    df = make_ohlcv()
    out = calculate_features(df)

    for col in ["momentum_5d", "momentum_20d", "distance_ema20", "volatility_20d"]:
        # Value at row i must be recomputable from data up to i only.
        for i in (30, 50, 100):
            prefix = df.iloc[: i + 1]
            prefix_out = calculate_features(prefix)
            assert out[col].iloc[i] == prefix_out[col].iloc[i], col


def test_nan_feature_behaviour_is_explicit():
    df = make_ohlcv()
    out = calculate_features(df)

    # First 60 rows have NaN for 60-day features; rolling/ewm handle this.
    assert out["momentum_60d"].iloc[:59].isna().all()
    assert not out["momentum_60d"].iloc[-1] != out["momentum_60d"].iloc[-1]

    # RSI is bounded for warm data.
    rsi = out["rsi_14"].dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        calculate_features(pd.DataFrame({"close": [1.0, 2.0]}))


def test_feature_version_tag():
    out = calculate_features(make_ohlcv())
    assert out.attrs["feature_version"] == FEATURE_VERSION
