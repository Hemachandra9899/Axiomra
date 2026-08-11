"""Pydantic schemas and dataclasses for Upstox API payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UpstoxInstrumentItem(BaseModel):
    """Raw record from Upstox BOD Instrument Master JSON file."""

    instrument_key: str
    trading_symbol: str
    name: str | None = None
    last_price: float | None = None
    strike_price: float | None = None
    tick_size: float | None = None
    lot_size: int | None = None
    instrument_type: str | None = None
    freeze_quantity: float | None = None
    exchange: str = "NSE"
    isin: str | None = None
    asset_symbol: str | None = None
    asset_key: str | None = None
    underlying_symbol: str | None = None
    underlying_key: str | None = None


class UpstoxCandleData(BaseModel):
    """Raw candle response wrapper from Upstox V3 Historical Candle API."""

    status: str = "success"
    data: dict[str, Any] = Field(default_factory=dict)
    """Contains 'candles': list of [timestamp, open, high, low, close, volume, open_interest]."""
