"""Runs independent research agents over a snapshot."""

from __future__ import annotations

from axiomra.agents.base import ResearchAgent, SkepticAgent
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import EvidenceSignal, SkepticReview


class ResearchOrchestrator:
    """Collects structured evidence from every research source."""

    def __init__(
        self,
        agents: list[ResearchAgent] | None = None,
        skeptic: SkepticAgent | None = None,
    ) -> None:
        self.agents = agents or []
        self.skeptic = skeptic

    async def research(self, snapshot: MarketSnapshot) -> list[EvidenceSignal]:
        """Run all agents. One failure does not discard the others."""
        signals: list[EvidenceSignal] = []
        for agent in self.agents:
            try:
                signals.append(await agent.analyze(snapshot))
            except Exception as exc:  # pragma: no cover - resilient by design
                signals.append(
                    EvidenceSignal(
                        source=agent.name,
                        score=0.0,
                        confidence=0.0,
                        risks=[f"agent failed: {exc}"],
                    )
                )
        return signals

    async def skepticism(
        self,
        snapshot: MarketSnapshot,
        candidate: EvidenceSignal,
    ) -> SkepticReview | None:
        if self.skeptic is None:
            return None
        return await self.skeptic.review(snapshot, candidate)
