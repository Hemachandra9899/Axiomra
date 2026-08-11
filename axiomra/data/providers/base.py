"""Data provider interfaces.

Axiomra's internal data contracts are independent of any specific vendor.
Providers (OpenBB, yfinance, broker APIs, ...) implement these interfaces;
they never leak through the rest of the system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from axiomra.domain.market import Bar, MarketSnapshot


class MarketDataProvider(ABC):
    """Historical and live OHLCV bars."""

    @abstractmethod
    async def bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1d",
    ) -> list[Bar]: ...

    @abstractmethod
    async def latest_snapshot(self, symbol: str) -> MarketSnapshot: ...


class FundamentalDataProvider(ABC):
    """Point-in-time fundamentals. Returns None for unknown fields."""

    @abstractmethod
    async def fundamentals(
        self,
        symbol: str,
        as_of: datetime,
    ) -> dict[str, float | None]: ...


class NewsDataProvider(ABC):
    """News events for a symbol."""

    @abstractmethod
    async def news(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, object]]: ...


class DataProvider(MarketDataProvider, FundamentalDataProvider, NewsDataProvider, ABC):
    """A provider that supplies all data kinds (e.g. OpenBB adapter)."""
