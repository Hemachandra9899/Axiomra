"""Decision orchestration.

The DecisionEngine produces *candidates*. Portfolio construction, risk and
execution happen afterward. This module never touches a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel

from axiomra.agents.orchestrator import ResearchOrchestrator
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import (
    EvidenceSignal,
    QuantPrediction,
    SignalClassification,
    SkepticReview,
    TradeCandidate,
    classify_signal,
)
from axiomra.fusion.engine import FusionResult, SignalFusionEngine
from axiomra.quant.base import QuantModel
from axiomra.versions import (
    DECISION_ENGINE_VERSION,
    FUSION_VERSION,
    NO_TRADE_THRESHOLD,
)


class DecisionResult(BaseModel):
    """A fully researched candidate decision."""

    action: str
    symbol: str
    score: float
    raw_score: float
    confidence: float
    disagreement: float
    regime: str
    classification: SignalClassification
    candidate: TradeCandidate | None = None
    evidence: list[EvidenceSignal] = []
    skeptic: SkepticReview | None = None
    fusion: FusionResult | None = None


@dataclass
class DecisionConfig:
    no_trade_threshold: float = NO_TRADE_THRESHOLD


class DecisionEngine:
    """Analyzes one snapshot into an action candidate."""

    def __init__(
        self,
        quant_model: QuantModel,
        orchestrator: ResearchOrchestrator,
        fusion_engine: SignalFusionEngine,
        config: DecisionConfig | None = None,
    ) -> None:
        self.quant_model = quant_model
        self.orchestrator = orchestrator
        self.fusion = fusion_engine
        self.config = config or DecisionConfig()

        # Coverage is measured against the full panel of independent sources:
        # 1 quant model + every configured research agent. If agents are not
        # configured yet, a lone quant signal still counts as full coverage.
        self.fusion.config.expected_signal_count = max(
            1, 1 + len(orchestrator.agents)
        )

    async def analyze(self, snapshot: MarketSnapshot) -> DecisionResult:
        quant: QuantPrediction = await self.quant_model.predict(snapshot)

        agent_signals = await self.orchestrator.research(snapshot)
        signals = [quant, *agent_signals]

        self.fusion.set_regime(snapshot.market_regime)
        fused: FusionResult = self.fusion.fuse(signals)

        skeptic = await self.orchestrator.skepticism(snapshot, quant)

        confidence = fused.confidence
        raw_score = fused.raw_score
        if skeptic is not None:
            confidence *= skeptic.confidence_multiplier

        effective_score = raw_score * confidence
        classification = classify_signal(raw_score)

        if abs(effective_score) < self.config.no_trade_threshold:
            action = "NO_TRADE"
        elif effective_score > 0:
            action = "LONG"
        else:
            action = "REDUCE"

        candidate = TradeCandidate(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            decision_id=str(uuid4()),
            raw_score=raw_score,
            confidence=confidence,
            effective_score=effective_score,
            direction=classification.direction,
            evidence=signals,
            skeptic=skeptic,
            expected_return=quant.expected_return,
            regime=snapshot.market_regime,
            data_version=snapshot.data_version,
            model_versions={
                **self.quant_model.model_versions(),
                "fusion_version": FUSION_VERSION,
                "decision_version": DECISION_ENGINE_VERSION,
            },
        )

        return DecisionResult(
            action=action,
            symbol=snapshot.symbol,
            score=effective_score,
            raw_score=raw_score,
            confidence=confidence,
            disagreement=fused.disagreement,
            regime=snapshot.market_regime,
            classification=classification,
            candidate=candidate,
            evidence=signals,
            skeptic=skeptic,
            fusion=fused,
        )
