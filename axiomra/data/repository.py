"""Persistence contract.

The repository owns point-in-time correctness: bars, predictions, decisions
and outcomes are immutable once written. Re-reading history must reproduce
the exact state Axiomra saw at decision time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from axiomra.domain.market import Bar
from axiomra.domain.orders import ExecutionResult
from axiomra.domain.portfolio import PortfolioProposal
from axiomra.domain.signals import EvidenceSignal, TradeCandidate
from axiomra.risk.engine import RiskDecision


class DataRepository(ABC):
    """Storage for bars, decisions, orders and outcomes."""

    @abstractmethod
    async def insert_bars(self, bars: list[Bar]) -> int: ...

    @abstractmethod
    async def bars(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]: ...

    @abstractmethod
    async def save_decision(
        self,
        candidate: TradeCandidate,
        signals: list[EvidenceSignal],
        proposal: PortfolioProposal | None,
        risk: RiskDecision | None,
        execution: ExecutionResult | None,
    ) -> str: ...
