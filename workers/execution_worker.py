"""Execution worker — submits approved orders and tracks fills."""

from __future__ import annotations

from axiomra.domain.orders import ExecutionResult, OrderRequest
from axiomra.execution.base import ExecutionEngine


class ExecutionWorker:
    """Only receives orders that already passed Axiomra Guard."""

    def __init__(self, execution_engine: ExecutionEngine) -> None:
        self.execution = execution_engine

    async def submit(self, order: OrderRequest) -> ExecutionResult:
        return await self.execution.submit(order)

    async def cancel(self, order_id: str) -> bool:
        return await self.execution.cancel(order_id)
