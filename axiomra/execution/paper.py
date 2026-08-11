"""Paper execution engine.

Simulates orders with optional slippage, fees, and partial fills so the whole
pipeline can run without touching real money.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

from axiomra.domain.orders import ExecutionResult, OrderRequest, OrderSide, OrderStatus
from axiomra.execution.base import ExecutionEngine


@dataclass
class PaperExecutionConfig:
    slippage_bps: float = 0.0
    fee_bps: float = 0.0
    reject_probability: float = 0.0
    partial_fill_probability: float = 0.0
    partial_fill_ratio: float = 0.5
    reference_price: float | None = None


class PaperExecutionEngine(ExecutionEngine):
    """Deterministic-ish simulated execution for research and testing."""

    def __init__(
        self,
        config: PaperExecutionConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.config = config or PaperExecutionConfig()
        self.rng = rng or random.Random(0)
        self._orders: dict[str, OrderRequest] = {}

    async def submit(self, order: OrderRequest) -> ExecutionResult:
        cfg = self.config
        order_id = str(uuid.uuid4())
        self._orders[order_id] = order

        if cfg.reject_probability > 0 and self.rng.random() < cfg.reject_probability:
            return ExecutionResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                message="simulated rejection",
            )

        price = cfg.reference_price
        if price is None:
            price = order.limit_price
        if price is None:
            price = 100.0  # placeholder; use MarketDataProvider for real runs

        slippage = price * cfg.slippage_bps / 10_000
        fill_price = (
            max(0.01, price - slippage)
            if order.side == OrderSide.BUY
            else max(0.01, price + slippage)
        )

        filled = order.quantity
        status = OrderStatus.FILLED
        if cfg.partial_fill_probability > 0 and self.rng.random() < cfg.partial_fill_probability:
            filled = int(order.quantity * cfg.partial_fill_ratio)
            status = OrderStatus.PARTIALLY_FILLED

        return ExecutionResult(
            order_id=order_id,
            status=status,
            filled_quantity=filled,
            avg_fill_price=fill_price,
            message="FILLED_SIMULATED",
            raw={"fee_bps": cfg.fee_bps},
        )

    async def cancel(self, order_id: str) -> bool:
        return order_id in self._orders
