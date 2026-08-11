"""Order and execution domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(StrEnum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class OrderRequest(BaseModel):
    """An order proposal that has already passed Axiomra Guard.

    Order requests are only created by the portfolio engine after risk
    approval. Research, agents and quant models never construct these.
    """

    symbol: str
    side: OrderSide
    quantity: int = Field(gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)
    decision_id: str | None = None
    created_at: datetime | None = None


class ExecutionResult(BaseModel):
    """Outcome of submitting an order to an execution engine."""

    order_id: str
    status: OrderStatus
    filled_quantity: int = Field(default=0, ge=0)
    avg_fill_price: float | None = None
    message: str = ""
    raw: dict[str, object] = Field(default_factory=dict)

    @property
    def is_filled(self) -> bool:
        return self.status in {"FILLED", "PARTIALLY_FILLED"}
