"""M4: outcome attribution and Bayesian source reliability."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axiomra.attribution.engine import (
    attribute_outcomes,
    build_source_reliability,
)
from axiomra.fusion.engine import SignalFusionEngine
from axiomra.memory.journal import JournalEntry


def _entry(
    decision_id: str,
    symbol: str,
    regime: str,
    outcome: float | None,
    sources: list[str],
    confidence: float = 0.5,
) -> JournalEntry:
    return JournalEntry(
        decision_id=decision_id,
        symbol=symbol,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        data_version="d1",
        feature_version="f1",
        regime=regime,
        confidence=confidence,
        proposed_action="LONG",
        risk_status="APPROVED",
        evidence=[{"source": s, "score": 0.5, "confidence": 0.5} for s in sources],
        outcome_return_pct=outcome,
    )


def test_attribution_segments_by_regime_and_source():
    entries = [
        _entry("1", "AAA.NS", "TREND_UP", 0.05, ["quant", "technical"]),
        _entry("2", "AAA.NS", "TREND_UP", -0.02, ["quant"]),
        _entry("3", "BBB.NS", "RANGE", 0.01, ["fundamental"]),
        _entry("4", "CCC.NS", "TREND_DOWN", None, ["quant"]),  # no outcome
    ]
    report = attribute_outcomes(entries, sector_of={"AAA.NS": "Energy"})

    overall = report.segments("overall")
    assert len(overall) == 1
    assert overall[0].n == 3  # outcome-less entry excluded

    regime = {seg.key: seg for seg in report.segments("regime")}
    assert regime["TREND_UP"].n == 2
    assert regime["TREND_UP"].hits == 1
    assert regime["TREND_UP"].hit_rate == pytest.approx(
        (1 + 1) / (2 + 1 + 1)
    )  # alpha=beta=1

    sources = {seg.key: seg for seg in report.segments("source")}
    assert sources["quant"].n == 2  # appears in two decisions
    assert sources["technical"].n == 1

    sectors = {seg.key: seg for seg in report.segments("sector")}
    assert sectors["Energy"].n == 2
    assert sectors["UNKNOWN"].n == 1


def test_small_samples_shrink_toward_prior():
    entries = [
        _entry("1", "AAA.NS", "RANGE", 0.05, ["quant"]),
    ]
    report = attribute_outcomes(entries)
    seg = report.segments("source")[0]
    assert seg.raw_hit_rate == 1.0  # 1/1
    assert seg.hit_rate < 0.9  # shrunk by the prior, not 1.0


def test_source_reliability_clamps_to_floor_ceiling():
    entries = [_entry("1", "AAA.NS", "RANGE", 0.05, ["quant"])]
    report = attribute_outcomes(entries)
    rel = build_source_reliability(report)
    assert 0.0 < rel["quant"] < 1.0
    assert 0.10 <= rel["quant"] <= 0.95

    tiny = build_source_reliability(report, floor=0.3, ceiling=0.7)
    assert 0.3 <= tiny["quant"] <= 0.7


def test_reliability_feeds_fusion_weighting():
    # A source that mostly got it right should weigh more after smoothing.
    entries = [
        _entry(f"{i}", "AAA.NS", "TREND_UP", 0.03 if i < 8 else -0.01, ["quant"])
        for i in range(10)
    ]
    report = attribute_outcomes(entries)
    rel = build_source_reliability(report)
    assert rel["quant"] > 0.5  # 8/10 raw, smoothed up from the 0.5 prior

    engine = SignalFusionEngine()
    engine.set_reliability("quant", rel["quant"])
    engine_default = SignalFusionEngine()

    from axiomra.domain.signals import EvidenceSignal

    signal = EvidenceSignal(source="quant", score=0.7, confidence=0.8)
    w_with_history = engine.config.effective_weight(signal)
    w_default = engine_default.config.effective_weight(signal)
    assert w_with_history > w_default
