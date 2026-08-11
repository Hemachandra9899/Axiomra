"""Outcome attribution.

After a trade closes we ask: which evidence source actually contributed
predictive value? Over thousands of observations these statistics feed the
fusion engine's reliability weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from axiomra.domain.signals import EvidenceSignal


@dataclass
class SourceAttribution:
    """Empirical reliability of one evidence source."""

    source: str
    observations: int = 0
    correct_direction: int = 0
    sum_weighted_contribution: float = 0.0

    @property
    def reliability(self) -> float:
        """Share of observations where the source agreed with the outcome."""
        if self.observations == 0:
            return 0.50
        return self.correct_direction / self.observations


@dataclass
class AttributionEngine:
    """Accumulates source performance from closed trades."""

    sources: dict[str, SourceAttribution] = field(default_factory=dict)

    def record(
        self,
        signals: list[EvidenceSignal],
        outcome_return_pct: float,
        success_threshold_pct: float = 0.0,
    ) -> None:
        """Record one closed trade against its evidence.

        A source agrees if its sign matches the sign of the outcome (or the
        outcome beats the success threshold).
        """
        positive = outcome_return_pct > success_threshold_pct
        for signal in signals:
            attribution = self.sources.setdefault(
                signal.source, SourceAttribution(source=signal.source)
            )
            attribution.observations += 1
            signed = signal.score > 0
            if signed == positive:
                attribution.correct_direction += 1

    def reliability(self) -> dict[str, float]:
        return {
            source: attribution.reliability
            for source, attribution in self.sources.items()
        }

    def by_source(self, source: str) -> SourceAttribution:
        return self.sources.get(source, SourceAttribution(source=source))
