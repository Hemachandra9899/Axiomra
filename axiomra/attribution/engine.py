"""Decision attribution.

Where did Axiomra get it right? Attribution segments journaled outcomes
by regime, sector, evidence source and overall, then applies Bayesian
smoothing so small samples shrink toward the prior instead of producing
extreme reliability numbers that would distort fusion weights.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from axiomra.memory.journal import JournalEntry


class Segment(BaseModel):
    """One attributed slice of the decision history."""

    dimension: str
    key: str
    n: int
    hits: int
    raw_hit_rate: float
    hit_rate: float  # Bayes-smoothed toward 0.5
    avg_return: float
    confidence_sum: float = 0.0


class AttributionReport(BaseModel):
    """Attribution grouped by dimension."""

    generated_at: datetime
    dimensions: dict[str, list[Segment]] = Field(default_factory=dict)

    def segments(self, dimension: str) -> list[Segment]:
        return self.dimensions.get(dimension, [])


def _smooth_hit_rate(hits: int, n: int, alpha: float = 1.0, beta: float = 1.0) -> float:
    """Beta posterior mean: (hits + alpha) / (n + alpha + beta).

    With alpha = beta = 1 the estimate shrinks toward 0.5 as n -> 0 and
    approaches the raw rate as n grows.
    """
    if n <= 0:
        return 0.5
    return (hits + alpha) / (n + alpha + beta)


def _is_hit(entry: JournalEntry) -> bool:
    """A long-only decision hits when the forward return is positive.

    V1 is long-only; direction-aware hits arrive with short exposure.
    """
    if entry.outcome_return_pct is None:
        return False
    return entry.outcome_return_pct > 0.0


def _add_segment(
    dims: dict[str, dict[str, dict]], dimension: str, key: str, entry: JournalEntry
) -> None:
    bucket = dims.setdefault(dimension, {}).setdefault(key, {"n": 0, "hits": 0, "ret": 0.0, "conf": 0.0})
    bucket["n"] += 1
    if _is_hit(entry):
        bucket["hits"] += 1
    bucket["ret"] += entry.outcome_return_pct or 0.0
    bucket["conf"] += entry.confidence


def _finalize(
    dims: dict[str, dict[str, dict]], alpha: float, beta: float
) -> dict[str, list[Segment]]:
    out: dict[str, list[Segment]] = {}
    for dimension, buckets in dims.items():
        segments = []
        for key, b in sorted(buckets.items()):
            n = b["n"]
            raw = b["hits"] / n if n else 0.0
            segments.append(
                Segment(
                    dimension=dimension,
                    key=key,
                    n=n,
                    hits=b["hits"],
                    raw_hit_rate=round(raw, 4),
                    hit_rate=round(_smooth_hit_rate(b["hits"], n, alpha, beta), 4),
                    avg_return=round(b["ret"] / n, 6) if n else 0.0,
                    confidence_sum=round(b["conf"], 4),
                )
            )
        out[dimension] = segments
    return out


def attribute_outcomes(
    entries: list[JournalEntry],
    sector_of: dict[str, str] | None = None,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> AttributionReport:
    """Segment journaled decisions by regime, sector, source and overall."""
    dims: dict[str, dict[str, dict]] = {}

    for entry in entries:
        if entry.outcome_return_pct is None:
            continue

        _add_segment(dims, "overall", "all", entry)
        _add_segment(dims, "regime", entry.regime or "UNKNOWN", entry)

        if sector_of:
            _add_segment(dims, "sector", sector_of.get(entry.symbol, "UNKNOWN"), entry)

        for signal in entry.evidence:
            source = signal.get("source") or "unknown"
            _add_segment(dims, "source", source, entry)

    return AttributionReport(
        generated_at=datetime.now(UTC),
        dimensions=_finalize(dims, alpha, beta),
    )


def build_source_reliability(
    report: AttributionReport,
    floor: float = 0.10,
    ceiling: float = 0.95,
) -> dict[str, float]:
    """Smoothed per-source reliability for fusion weighting.

    Clamped into [floor, ceiling] so no source is fully trusted or fully
    ignored regardless of sample size.
    """
    result: dict[str, float] = {}
    for seg in report.segments("source"):
        result[seg.key] = min(ceiling, max(floor, seg.hit_rate))
    return result
