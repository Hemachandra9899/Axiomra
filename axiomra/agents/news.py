"""News analysis agent.

News sentiment alone is not enough: positive news can already be priced in.
The agent scores direction, importance, novelty, duration and confidence.
"""

from __future__ import annotations

from axiomra.agents.base import AgentReasoner, ResearchAgent, StructuredOutput
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import EvidenceSignal

SYSTEM_PROMPT = """\
You are Axiomra's news analyst.

Evaluate ONLY the supplied news evidence. Do not make portfolio or order
decisions.

Return:
score [-1,1], confidence [0,1], reasons, risks

Consider direction, importance, novelty, expected duration, and whether the
news is likely already priced in. Reduce score for stale or low-novelty news.
"""


class NewsAgent(ResearchAgent):
    name = "news"

    def __init__(self, reasoner: AgentReasoner) -> None:
        self._reasoner = reasoner

    async def analyze(self, snapshot: MarketSnapshot) -> EvidenceSignal:
        news = [
            {k: v for k, v in item.items() if k in {"headline", "ts", "source"}}
            for item in getattr(snapshot, "news", []) or []
        ]
        out: StructuredOutput = await self._reasoner(SYSTEM_PROMPT, {"news": news})
        return EvidenceSignal(
            source=self.name,
            score=out.score,
            confidence=out.confidence,
            reasons=out.reasons,
            risks=out.risks,
        )
