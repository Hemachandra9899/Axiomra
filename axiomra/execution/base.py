"""Execution engine contract.

Only this path may touch an execution venue: Research -> Fusion -> Portfolio
-> Guard -> Execution. Engines are pluggable: PaperExecutionEngine,
LeanExecutionEngine, BrokerExecutionEngine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from axiomra.domain.orders import ExecutionResult, OrderRequest


class ExecutionEngine(ABC):
    """Abstract order submission."""

    @abstractmethod
    async def submit(self, order: OrderRequest) -> ExecutionResult: ...

    @abstractmethod
    async def cancel(self, order_id: str) -> bool: ...
