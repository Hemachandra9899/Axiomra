"""Research agent contracts.

Agents evaluate evidence and return structured signals. They never produce
orders, quantities or broker calls. A `reasoner` abstracts the LLM so agents
stay testable without network access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import Protocol

from pydantic import BaseModel, Field

from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import EvidenceSignal, SkepticReview


class StructuredOutput(BaseModel):
    """Validated shape an agent must return."""

    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    extra: dict[str, object] = Field(default_factory=dict)


class AgentReasoner(Protocol):
    """Callable that turns a prompt into structured agent output."""

    def __call__(
        self, system_prompt: str, context: dict[str, object]
    ) -> Awaitable[StructuredOutput]: ...


class ResearchAgent(ABC):
    """A source of independent evidence about one symbol."""

    name: str = "base"

    @abstractmethod
    async def analyze(self, snapshot: MarketSnapshot) -> EvidenceSignal: ...


class SkepticAgent(ABC):
    """Raises objections; does not vote."""

    name: str = "skeptic"

    @abstractmethod
    async def review(
        self,
        snapshot: MarketSnapshot,
        candidate: EvidenceSignal,
    ) -> SkepticReview: ...
