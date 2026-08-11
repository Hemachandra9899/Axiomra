"""Technical analysis agent."""

from __future__ import annotations

from axiomra.agents.base import AgentReasoner, ResearchAgent, StructuredOutput
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import EvidenceSignal

SYSTEM_PROMPT = """\
You are Axiomra's technical analyst.

Evaluate ONLY the supplied evidence. Do not make portfolio or order decisions.

Return:
score [-1,1], confidence [0,1], reasons, risks

Evaluate: trend, momentum, volatility, volume, relative strength.
"""


class TechnicalAgent(ResearchAgent):
    name = "technical"

    def __init__(self, reasoner: AgentReasoner) -> None:
        self._reasoner = reasoner

    async def analyze(self, snapshot: MarketSnapshot) -> EvidenceSignal:
        context = {
            "features": {
                k: v
                for k, v in snapshot.features.items()
                if k in {"momentum_5d", "momentum_20d", "momentum_60d", "distance_ema20", "rsi_14", "atr_14", "volume_ratio"}
            }
        }
        out: StructuredOutput = await self._reasoner(SYSTEM_PROMPT, context)
        return EvidenceSignal(
            source=self.name,
            score=out.score,
            confidence=out.confidence,
            reasons=out.reasons,
            risks=out.risks,
        )
