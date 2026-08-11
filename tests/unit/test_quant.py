"""Quant engine unit tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axiomra.domain.market import OHLCV, MarketSnapshot
from axiomra.domain.signals import QuantPrediction
from axiomra.quant.base import QuantEnsemble
from axiomra.quant.calibration import CalibrationTable, Calibrator
from axiomra.quant.ensemble import ensemble_quant
from axiomra.quant.momentum import MomentumBaseline


def _snapshot(features: dict) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="RELIANCE.NS",
        timestamp=datetime.now(UTC),
        bar=OHLCV(open=100, high=105, low=99, close=102, volume=1_000_000),
        features=features,
        data_version="test-v1",
    )


BASE = {
    "momentum_5d": 0.04,
    "momentum_20d": 0.10,
    "momentum_60d": 0.25,
    "volatility_20d": 0.02,
    "volume_ratio": 1.4,
    "distance_ema20": 0.03,
    "ret_1d": 0.01,
}


async def test_momentum_baseline_score_and_bounds():
    model = MomentumBaseline()
    pred = await model.predict(_snapshot(BASE))
    assert isinstance(pred, QuantPrediction)
    assert -1.0 <= pred.score <= 1.0
    assert 0.0 <= pred.confidence <= 1.0
    assert pred.model_name == "momentum"


async def test_momentum_baseline_missing_feature_raises():
    model = MomentumBaseline()
    with pytest.raises(ValueError):
        await model.predict(_snapshot({}))


def test_ensemble_quant_weighted():
    assert ensemble_quant([(0.70, 0.5), (0.30, 0.5)]) == pytest.approx(0.5)
    assert ensemble_quant([(1.0, 0.9), (0.0, 0.1)]) == pytest.approx(0.9)


def test_ensemble_quant_zero_weight_raises():
    with pytest.raises(ValueError):
        ensemble_quant([(0.5, 0.0)])


async def test_quant_ensemble_combines_models():
    class Fixed(QuantEnsemble):
        pass

    class M1:
        name = "m1"
        version = "v1"

        async def predict(self, snapshot):
            return QuantPrediction(
                source="q_m1",
                symbol=snapshot.symbol,
                score=0.8,
                confidence=0.9,
                model_name="m1",
                model_version="v1",
            )

    class M2:
        name = "m2"
        version = "v1"

        async def predict(self, snapshot):
            return QuantPrediction(
                source="q_m2",
                symbol=snapshot.symbol,
                score=0.2,
                confidence=0.5,
                model_name="m2",
                model_version="v1",
            )

    ensemble = QuantEnsemble(models=[M1(), M2()], weights={"m1": 0.75, "m2": 0.25})
    pred = await ensemble.predict(_snapshot(BASE))
    assert pred.score == pytest.approx(0.65)
    assert pred.confidence == pytest.approx(0.7)


def test_calibration_build_and_lookup():
    scores = [0.35, 0.45, 0.55, 0.65, 0.85, 0.85]
    returns = [-0.001, 0.003, 0.004, 0.009, 0.014, 0.016]
    table = CalibrationTable.build(scores, returns)
    calibrator = Calibrator(table)

    bucket = table.lookup(0.7)
    assert bucket is not None
    assert bucket.count == 3  # 0.65, 0.85, 0.85 fall in [0.6, 1.0]
    assert bucket.mean_return == pytest.approx((0.009 + 0.014 + 0.016) / 3)
    assert bucket.win_rate == 1.0

    assert calibrator.expected_return(0.7) == pytest.approx((0.009 + 0.014 + 0.016) / 3)


def test_calibration_empty():
    assert CalibrationTable.build([], []).buckets == []
