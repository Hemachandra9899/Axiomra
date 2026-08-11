"""Decision worker — turns candidates into guarded, sized proposals."""

from __future__ import annotations

from axiomra.domain.market import MarketSnapshot
from axiomra.pipeline import AxiomraPipeline, PipelineContext


class DecisionWorker:
    """Applies the full decision -> portfolio -> guard chain."""

    def __init__(self, pipeline: AxiomraPipeline) -> None:
        self.pipeline = pipeline

    async def process(
        self,
        snapshot: MarketSnapshot,
        ctx: PipelineContext,
    ):
        return await self.pipeline.run(snapshot, ctx)
