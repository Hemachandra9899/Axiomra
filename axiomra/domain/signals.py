"""Structured signals.

Everything produced by Axiomra — quant models, AI agents, the fusion engine —
must be structured data. No free-form agent prose flows between components.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from axiomra.domain.common import as_utc

Direction = Literal["LONG", "SHORT", "NEUTRAL"]


class Regime(StrEnum):
    """Market regime labels used across Axiomra."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"


class EvidenceSignal(BaseModel):
    """A single source's view of one symbol.

    score:      -1 strongly bearish .. +1 strongly bullish
    confidence:  0 no trust .. 1 full trust
    """

    source: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class QuantPrediction(EvidenceSignal):
    """Output of a single quant model."""

    symbol: str
    expected_return: float | None = None
    model_name: str
    model_version: str


class SkepticReview(BaseModel):
    """Independent objections raised against a candidate thesis.

    The skeptic does not vote; it reduces confidence.
    """

    severity: float = Field(ge=0.0, le=1.0)
    objections: list[str] = Field(default_factory=list)
    invalidations: list[str] = Field(default_factory=list)

    @property
    def has_objections(self) -> bool:
        return len(self.objections) + len(self.invalidations) > 0

    @property
    def confidence_multiplier(self) -> float:
        if not self.has_objections:
            return 1.0
        return max(0.0, 1.0 - self.severity)


class TradeCandidate(BaseModel):
    """A fully researched candidate. Not yet a trade.

    Portfolio construction and risk evaluation happen after this object.
    """

    symbol: str
    timestamp: datetime

    decision_id: str | None = None

    raw_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    effective_score: float = Field(ge=-1.0, le=1.0)

    direction: Direction

    evidence: list[EvidenceSignal] = Field(default_factory=list)
    skeptic: SkepticReview | None = None

    expected_return: float | None = None

    regime: Regime
    data_version: str
    model_versions: dict[str, str] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _utc_ts(cls, value: datetime) -> datetime:
        return as_utc(value)


class SignalClassification(BaseModel):
    """Mapping from a fused score to an action label."""

    label: str
    score: float
    direction: Direction


def classify_signal(score: float) -> SignalClassification:
    """Large no-trade region keeps costs and noise out.

    For the V1 cash-equity product, SHORT / STRONG_SHORT simply mean
    "reduce or do not hold". Actual short selling is not enabled.
    """
    if score >= 0.60:
        return SignalClassification(label="STRONG_LONG", score=score, direction="LONG")
    if score >= 0.30:
        return SignalClassification(label="LONG", score=score, direction="LONG")
    if score <= -0.60:
        return SignalClassification(label="STRONG_SHORT", score=score, direction="SHORT")
    if score <= -0.30:
        return SignalClassification(label="SHORT", score=score, direction="SHORT")
    return SignalClassification(label="NO_TRADE", score=score, direction="NEUTRAL")
