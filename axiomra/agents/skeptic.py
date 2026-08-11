"""Independent risk skeptic.

The skeptic does not vote on the trade. It returns objections that reduce
the candidate's confidence.
"""

from __future__ import annotations

from axiomra.agents.base import AgentReasoner, SkepticAgent
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import EvidenceSignal, SkepticReview

SYSTEM_PROMPT = """\
You are Axiomra's independent risk skeptic.

Your job is NOT to support the thesis. Find evidence that could invalidate
it. Look for contradictory data, event risk, overvaluation, crowding, weak
liquidity, abnormal volatility, correlation with current holdings, and stale
evidence.

Return structured objections only — no trade recommendation.
"""


class SkepticReviewAgent(SkepticAgent):
    name = "skeptic"

    def __init__(self, reasoner: AgentReasoner) -> None:
        self._reasoner = reasoner

    async def review(
        self,
        snapshot: MarketSnapshot,
        candidate: EvidenceSignal,
    ) -> SkepticReview:
        context = {
            "candidate_score": candidate.score,
            "candidate_reasons": candidate.reasons,
            "features": snapshot.features,
            "event_risk_hint": bool(snapshot.news),
        }
        out = await self._reasoner(SYSTEM_PROMPT, context)

        objections = out.reasons or []
        invalidations = out.risks or []

        severity_raw = out.extra.get("severity", 0.5)
        if isinstance(severity_raw, (int, float)):
            severity = float(severity_raw)
        else:
            severity = 0.5
        severity = min(1.0, max(0.0, severity))

        return SkepticReview(
            severity=float(severity),
            objections=objections,
            invalidations=invalidations,
        )
