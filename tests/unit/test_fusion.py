"""Fusion engine: weights, regime, disagreement, confidence."""

from __future__ import annotations

import pytest

from axiomra.domain.signals import EvidenceSignal, Regime
from axiomra.fusion.engine import (
    BASE_WEIGHTS,
    FusionConfig,
    SignalFusionEngine,
    fuse_signals,
)


def test_all_agree_high_confidence():
    signals = [
        EvidenceSignal(source="quant", score=0.7, confidence=0.9),
        EvidenceSignal(source="technical", score=0.6, confidence=0.8),
        EvidenceSignal(source="fundamental", score=0.5, confidence=0.7),
    ]
    result = fuse_signals(signals)
    assert 0.3 < result.raw_score < 0.7
    assert result.confidence > 0.5


def test_disagreement_reduces_confidence():
    agreeing = [
        EvidenceSignal(source="quant", score=0.7, confidence=1.0),
        EvidenceSignal(source="technical", score=0.7, confidence=1.0),
        EvidenceSignal(source="fundamental", score=0.7, confidence=1.0),
    ]
    clashing = [
        EvidenceSignal(source="quant", score=0.7, confidence=1.0),
        EvidenceSignal(source="technical", score=-0.7, confidence=1.0),
        EvidenceSignal(source="fundamental", score=-0.7, confidence=1.0),
    ]
    agree = fuse_signals(agreeing)
    clash = fuse_signals(clashing)
    assert agree.confidence > clash.confidence
    assert clash.disagreement > 0
    assert agree.effective_score > clash.effective_score


def test_zero_weight_signals_ignored():
    signals = [
        EvidenceSignal(source="quant", score=1.0, confidence=1.0),
        EvidenceSignal(source="news", score=-1.0, confidence=1.0),
    ]
    result = fuse_signals(signals)
    assert result.raw_score > 0  # quant dominates


def test_empty_signals_neutral():
    result = fuse_signals([])
    assert result.raw_score == 0.0
    assert result.confidence == 0.0


def test_regime_reliability_changes_weighting():
    cfg_trend = FusionConfig(regime=Regime.TREND_UP)
    cfg_range = FusionConfig(regime=Regime.RANGE)

    s = EvidenceSignal(source="quant", score=0.8, confidence=0.9)

    w_trend = cfg_trend.effective_weight(s)
    w_range = cfg_range.effective_weight(s)
    assert w_trend > w_range


def test_signal_fusion_engine_wrappers():
    engine = SignalFusionEngine()
    engine.set_regime(Regime.TREND_UP)
    result = engine.fuse(
        [EvidenceSignal(source="quant", score=0.5, confidence=0.8)]
    )
    assert result.raw_score == 0.5


def test_low_confidence_single_signal_stays_low():
    """One weak source must not produce high confidence just because there is
    nothing to disagree with."""
    result = fuse_signals(
        [EvidenceSignal(source="quant", score=0.8, confidence=0.10)]
    )
    assert result.disagreement == pytest.approx(0.0, abs=1e-9)
    assert result.confidence <= 0.10
    assert result.effective_score < 0.1


def test_low_confidence_agreeing_signals_stay_low():
    result = fuse_signals(
        [
            EvidenceSignal(source="quant", score=0.8, confidence=0.10),
            EvidenceSignal(source="technical", score=0.7, confidence=0.10),
            EvidenceSignal(source="fundamental", score=0.7, confidence=0.10),
        ]
    )
    assert result.confidence <= 0.10 * 1.0 * (3 / 4) + 1e-9


def test_high_confidence_agreeing_signals_are_high():
    result = fuse_signals(
        [
            EvidenceSignal(source="quant", score=0.7, confidence=0.9),
            EvidenceSignal(source="technical", score=0.7, confidence=0.9),
            EvidenceSignal(source="fundamental", score=0.7, confidence=0.9),
            EvidenceSignal(source="news", score=0.7, confidence=0.9),
        ]
    )
    assert result.confidence > 0.6
    assert result.disagreement < 0.1


def test_coverage_penalizes_missing_panel():
    """With a full panel expected, a single strong source is not trusted."""
    cfg = FusionConfig(expected_signal_count=5)
    result = fuse_signals(
        [EvidenceSignal(source="quant", score=0.8, confidence=0.9)],
        cfg,
    )
    assert result.confidence == pytest.approx(0.9 * (1 / 5))


def test_base_weights_are_positive():
    for source, weight in BASE_WEIGHTS.items():
        assert weight > 0, source
