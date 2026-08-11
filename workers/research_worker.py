"""Research worker — runs the daily quant ranking and research funnel.

Sketch: pulls NIFTY 200 snapshots, scores with the quant engine, filters to
the top candidates, then runs AI research only on those candidates.
"""

from __future__ import annotations

from axiomra.decision import DecisionEngine
from axiomra.domain.market import MarketSnapshot


class ResearchWorker:
    """Offline, scheduled research over the candidate universe."""

    def __init__(self, decision_engine: DecisionEngine, top_n: int = 40) -> None:
        self.decisions = decision_engine
        self.top_n = top_n

    async def score_universe(
        self,
        snapshots: list[MarketSnapshot],
    ) -> list[tuple[MarketSnapshot, float]]:
        """Cheap quant pass over the whole universe."""
        ranked: list[tuple[MarketSnapshot, float]] = []
        for snapshot in snapshots:
            signal = await self.decisions.quant_model.predict(snapshot)
            ranked.append((snapshot, signal.score))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    async def research_candidates(
        self,
        ranked: list[tuple[MarketSnapshot, float]],
    ) -> list[object]:
        """Expensive AI pass limited to the top candidates."""
        return [
            await self.decisions.analyze(snapshot)
            for snapshot, _ in ranked[: self.top_n]
        ]
