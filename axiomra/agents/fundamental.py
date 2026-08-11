"""Fundamental analysis agent."""

from __future__ import annotations

from axiomra.agents.base import AgentReasoner, ResearchAgent, StructuredOutput
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import EvidenceSignal

SYSTEM_PROMPT = """\
You are Axiomra's fundamental analyst.

Evaluate ONLY fundamental evidence. Do not make portfolio or order decisions.

Return:
score [-1,1], confidence [0,1], reasons, risks

Evaluate: revenue, profit growth, margins, ROE, ROCE, debt, free cash flow,
valuation, management guidance.
"""


class FundamentalAgent(ResearchAgent):
    name = "fundamental"

    def __init__(self, reasoner: AgentReasoner) -> None:
        self._reasoner = reasoner

    async def analyze(self, snapshot: MarketSnapshot) -> EvidenceSignal:
        fundamentals = {
            k: v
            for k, v in snapshot.fundamentals.items()
            if k in {"roe", "roce", "debt_equity", "revenue_growth", "earnings_growth", "free_cash_flow", "pe", "pb"}
        }
        out: StructuredOutput = await self._reasoner(
            SYSTEM_PROMPT, {"fundamentals": fundamentals}
        )
        return EvidenceSignal(
            source=self.name,
            score=out.score,
            confidence=out.confidence,
            reasons=out.reasons,
            risks=out.risks,
        )
