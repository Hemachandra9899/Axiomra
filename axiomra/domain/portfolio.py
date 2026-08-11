"""Portfolio-level domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from axiomra.domain.orders import OrderRequest


class PositionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ProposalDirection(StrEnum):
    LONG = "LONG"
    REDUCE = "REDUCE"
    NEUTRAL = "NEUTRAL"


class Holding(BaseModel):
    """A current position in the book."""

    symbol: str
    quantity: int = Field(ge=0)
    avg_price: float = Field(gt=0)
    as_of: datetime
    status: PositionStatus = "OPEN"

    @property
    def market_value(self, last_price: float) -> float:
        return self.quantity * last_price


class PositionSize(BaseModel):
    """Final size decision for a single candidate."""

    symbol: str
    quantity: int = Field(ge=0)
    notional: float = Field(ge=0)
    target_weight: float = Field(ge=0.0, le=1.0)
    stop_price: float | None = None
    risk_budget: float = Field(ge=0)
    reason: str = ""


class PortfolioProposal(BaseModel):
    """Output of the portfolio engine. Input to Axiomra Guard."""

    symbol: str
    portfolio_value: float = Field(gt=0)
    direction: ProposalDirection

    position_size: PositionSize | None = None
    target_weight: float = Field(ge=0.0, le=1.0)

    current_position_pct: float = Field(ge=0.0)
    projected_position_pct: float = Field(ge=0.0)
    projected_sector_pct: float = Field(ge=0.0)
    projected_correlation_pct: float = Field(ge=0.0, default=0.0)

    order: OrderRequest | None = None
    reasons: list[str] = Field(default_factory=list)

    @property
    def has_order(self) -> bool:
        return self.order is not None


class RiskCheck(BaseModel):
    """Result of one deterministic risk rule."""

    name: str
    passed: bool
    reason: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
