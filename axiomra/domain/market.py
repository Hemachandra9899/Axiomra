"""Point-in-time market state.

Every model in the system must see the same immutable snapshot.
The `data_version` field is what makes predictions reproducible:

    What data did Axiomra see when it made this prediction?
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from axiomra.domain.common import as_utc
from axiomra.domain.signals import Regime


class OHLCV(BaseModel):
    """A single price/volume bar."""

    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)

    @field_validator("high", "low")
    @classmethod
    def _high_gte_low(cls, value: float, info) -> float:
        return value


class Bar(OHLCV):
    """An OHLCV bar anchored to a timestamp."""

    symbol: str
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def _utc_ts(cls, value: datetime) -> datetime:
        return as_utc(value)


class FeatureSnapshot(BaseModel):
    """Features computed for a symbol at a point in time.

    `computed_at` is when features were produced; `as_of` is the last bar
    used. Feature values must never depend on information after `as_of`.
    """

    symbol: str
    as_of: datetime
    computed_at: datetime
    values: dict[str, float]
    feature_version: str


class MarketSnapshot(BaseModel):
    """The complete, frozen market state for one symbol."""

    symbol: str
    timestamp: datetime

    bar: OHLCV

    features: dict[str, float] = Field(default_factory=dict)
    fundamentals: dict[str, float | None] = Field(default_factory=dict)
    news: list[dict[str, object]] = Field(default_factory=list)

    market_regime: Regime = Regime.UNKNOWN

    data_version: str
    feature_version: str = ""

    @field_validator("timestamp")
    @classmethod
    def _utc_ts(cls, value: datetime) -> datetime:
        return as_utc(value)

    @classmethod
    def at_utc_now(
        cls,
        symbol: str,
        bar: OHLCV,
        data_version: str,
        **kwargs,
    ) -> MarketSnapshot:
        return cls(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            bar=bar,
            data_version=data_version,
            **kwargs,
        )

    @property
    def required_features(self) -> set[str]:
        """Feature names this snapshot is expected to expose."""
        return {
            "ret_1d",
            "momentum_5d",
            "momentum_20d",
            "volatility_20d",
            "volume_ratio",
            "distance_ema20",
        }
