"""Evidence fusion.

Effective weight per source:

    base_weight
      x historical_reliability
      x regime_reliability
      x current confidence

Signal disagreement between sources reduces fused confidence, which creates
a large no-trade region instead of a "committee vote".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

from pydantic import BaseModel, Field

from axiomra.domain.signals import EvidenceSignal, Regime

BASE_WEIGHTS: dict[str, float] = {
    "quant": 0.55,
    "quant_ensemble": 0.55,
    "quant_lightgbm": 0.55,
    "quant_momentum": 0.55,
    "technical": 0.15,
    "fundamental": 0.15,
    "news": 0.10,
    "regime": 0.05,
}

# Per-regime reliability multipliers:  source -> {regime: multiplier}
REGIME_RELIABILITY: dict[str, dict[str, float]] = {
    "quant": {Regime.TREND_UP: 0.90, Regime.RANGE: 0.40, Regime.TREND_DOWN: 0.50},
    "quant_momentum": {Regime.TREND_UP: 0.90, Regime.RANGE: 0.40, Regime.TREND_DOWN: 0.50},
    "quant_ensemble": {Regime.TREND_UP: 0.90, Regime.RANGE: 0.40, Regime.TREND_DOWN: 0.50},
    "quant_lightgbm": {Regime.TREND_UP: 0.85, Regime.RANGE: 0.60, Regime.TREND_DOWN: 0.55},
    "technical": {Regime.TREND_UP: 0.75, Regime.RANGE: 0.55, Regime.TREND_DOWN: 0.65},
    "fundamental": {Regime.TREND_UP: 0.60, Regime.RANGE: 0.65, Regime.TREND_DOWN: 0.70},
    "news": {Regime.TREND_UP: 0.45, Regime.RANGE: 0.45, Regime.TREND_DOWN: 0.60},
}

# Per-regime default base-weight scaling when no historical reliability exists
# yet: source -> {regime: base weight}
REGIME_BASE_WEIGHT: dict[str, dict[str, float]] = {
    "quant": {Regime.TREND_UP: 0.55, Regime.RANGE: 0.45, Regime.TREND_DOWN: 0.50},
    "quant_ensemble": {Regime.TREND_UP: 0.55, Regime.RANGE: 0.45, Regime.TREND_DOWN: 0.50},
    "quant_lightgbm": {Regime.TREND_UP: 0.55, Regime.RANGE: 0.45, Regime.TREND_DOWN: 0.50},
    "quant_momentum": {Regime.TREND_UP: 0.55, Regime.RANGE: 0.45, Regime.TREND_DOWN: 0.50},
    "technical": {Regime.TREND_UP: 0.15, Regime.RANGE: 0.15, Regime.TREND_DOWN: 0.15},
    "fundamental": {Regime.TREND_UP: 0.15, Regime.RANGE: 0.15, Regime.TREND_DOWN: 0.15},
    "news": {Regime.TREND_UP: 0.10, Regime.RANGE: 0.10, Regime.TREND_DOWN: 0.10},
}


class FusionSource(BaseModel):
    source: str
    score: float
    confidence: float
    weight: float


class FusionResult(BaseModel):
    raw_score: float
    confidence: float
    effective_score: float
    disagreement: float
    sources: list[FusionSource] = Field(default_factory=list)


@dataclass
class FusionConfig:
    """Tunable fusion behaviour."""

    default_base_weight: float = 0.10
    default_reliability: float = 0.50
    expected_signal_count: int = 4
    regime: str = Regime.UNKNOWN
    historical_reliability: dict[str, float] = field(default_factory=dict)
    base_weights: dict[str, float] = field(default_factory=lambda: dict(BASE_WEIGHTS))
    regime_reliability: dict[str, dict[str, float]] = field(
        default_factory=lambda: REGIME_RELIABILITY
    )
    regime_base_weight: dict[str, dict[str, float]] = field(
        default_factory=lambda: REGIME_BASE_WEIGHT
    )

    def effective_weight(self, signal: EvidenceSignal) -> float:
        base = self.base_weights.get(
            signal.source,
            self.regime_base_weight.get(signal.source, {}).get(
                self.regime, self.default_base_weight
            ),
        )

        historical = self.historical_reliability.get(signal.source, self.default_reliability)
        regime = self.regime_reliability.get(signal.source, {}).get(self.regime, 1.0)
        return base * historical * regime * signal.confidence


def fuse_signals(
    signals: list[EvidenceSignal],
    config: FusionConfig | None = None,
) -> FusionResult:
    """Fuse independent evidence into a single (score, confidence)."""
    cfg = config or FusionConfig()

    weighted_scores: list[tuple[EvidenceSignal, float]] = []
    total_weight = 0.0

    for signal in signals:
        w = cfg.effective_weight(signal)
        if w <= 0:
            continue
        weighted_scores.append((signal, w))
        total_weight += w

    if not weighted_scores or total_weight <= 0:
        return FusionResult(
            raw_score=0.0,
            confidence=0.0,
            effective_score=0.0,
            disagreement=0.0,
        )

    raw_score = sum(sig.score * w for sig, w in weighted_scores) / total_weight

    # Weighted confidence: a strong source with low confidence must not produce
    # a confident fused signal just because nothing disagrees with it.
    weighted_confidence = (
        sum(sig.confidence * w for sig, w in weighted_scores) / total_weight
    )

    variance = (
        sum(w * (sig.score - raw_score) ** 2 for sig, w in weighted_scores)
        / total_weight
    )
    disagreement = min(1.0, sqrt(variance))
    agreement_factor = 1.0 - disagreement

    # Coverage: a single weak source should not carry the same confidence as a
    # full panel of independent sources.
    coverage = min(1.0, len(weighted_scores) / max(cfg.expected_signal_count, 1))

    confidence = max(0.0, weighted_confidence * agreement_factor * coverage)
    effective_score = raw_score * confidence

    sources = [
        FusionSource(
            source=sig.source,
            score=sig.score,
            confidence=sig.confidence,
            weight=w,
        )
        for sig, w in weighted_scores
    ]

    return FusionResult(
        raw_score=raw_score,
        confidence=confidence,
        effective_score=effective_score,
        disagreement=disagreement,
        sources=sources,
    )


class SignalFusionEngine:
    """Object-oriented wrapper around `fuse_signals`."""

    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()

    def fuse(self, signals: list[EvidenceSignal]) -> FusionResult:
        return fuse_signals(signals, self.config)

    def set_regime(self, regime: str) -> None:
        self.config.regime = regime

    def set_reliability(self, source: str, reliability: float) -> None:
        self.config.historical_reliability[source] = reliability
