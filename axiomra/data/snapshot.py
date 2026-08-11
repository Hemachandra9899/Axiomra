"""Immutable, checksummed dataset snapshots.

A `DatasetSnapshot` is the point-in-time state Axiomra commits to disk before
running a research/backtest session: the universe, every bar per symbol
(split-adjusted so history is comparable), and the corporate actions that
explain the adjustments. The checksum binds a session to its exact input data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from axiomra.data.instruments import CorporateAction
from axiomra.data.universe import IndexMembership, Universe
from axiomra.domain.common import as_utc
from axiomra.domain.market import Bar


class AdjustmentMode(StrEnum):

    """Price adjustment policy for point-in-time dataset snapshots."""

    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    TOTAL_RETURN = "total_return"


class DatasetSnapshot(BaseModel):
    """Frozen dataset: universe + adjusted bars + actions + memberships.

    Everything is a value object; `model_config = {"frozen": True}` prevents
    accidental mutation after the snapshot has been committed.
    """

    model_config = {"frozen": True}

    dataset_id: str
    universe: Universe
    data_version: str
    created_at: datetime
    checksum: str
    adjustment_mode: AdjustmentMode = AdjustmentMode.SPLIT_ADJUSTED
    bars: dict[str, list[Bar]] = Field(default_factory=dict)
    actions: list[CorporateAction] = Field(default_factory=list)
    memberships: list[IndexMembership] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        return as_utc(value)

    @model_validator(mode="after")
    def _checksum_matches(self) -> DatasetSnapshot:
        if self.checksum and self.checksum != compute_checksum(self):
            raise ValueError("checksum mismatch: snapshot content was mutated")
        return self

    def symbols(self) -> list[str]:
        return list(self.bars.keys())

    def symbol_count(self) -> int:
        return len(self.bars)

    def bar_count(self) -> int:
        return sum(len(bars) for bars in self.bars.values())


def _canonical_json(snapshot: DatasetSnapshot) -> str:
    """Deterministic serialization of content that the checksum covers."""
    payload = {
        "universe": {
            "name": snapshot.universe.name,
            "version": snapshot.universe.version,
            "as_of": snapshot.universe.as_of.isoformat(),
            "members": snapshot.universe.members,
        },
        "data_version": snapshot.data_version,
        "adjustment_mode": snapshot.adjustment_mode.value if hasattr(snapshot.adjustment_mode, "value") else str(snapshot.adjustment_mode),

        "bars": {
            symbol: [
                {
                    "symbol": b.symbol,
                    "timestamp": b.timestamp.isoformat(),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ]
            for symbol, bars in sorted(snapshot.bars.items())
        },
        "actions": [
            {
                "instrument_id": a.instrument_id,
                "action_type": a.action_type if isinstance(a.action_type, str) else a.action_type.value,
                "ex_date": a.ex_date.isoformat(),
                "ratio": a.ratio,
                "amount": a.amount,
                "note": a.note,
            }
            for a in sorted(snapshot.actions, key=lambda a: (a.instrument_id, a.ex_date.isoformat()))
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_checksum(snapshot: DatasetSnapshot) -> str:
    """SHA-256 over the canonical JSON of the snapshot content."""
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def build_dataset_id(checksum: str) -> str:
    """Short, content-addressed identifier for a dataset."""
    return f"ds-{checksum[:12]}"


def create_snapshot(
    universe: Universe,
    bars: dict[str, list[Bar]],
    data_version: str,
    actions: list[CorporateAction] | None = None,
    adjustment_mode: AdjustmentMode = AdjustmentMode.SPLIT_ADJUSTED,
    memberships: list[IndexMembership] | None = None,
) -> DatasetSnapshot:
    """Build a checksummed snapshot, deriving dataset_id from content."""
    snap = DatasetSnapshot(
        dataset_id="",
        universe=universe,
        data_version=data_version,
        created_at=datetime.now(UTC),
        checksum="",
        adjustment_mode=adjustment_mode,
        bars=bars,
        actions=actions or [],
        memberships=memberships or [],
    )
    checksum = compute_checksum(snap)
    return DatasetSnapshot.model_validate(
        {**snap.model_dump(), "dataset_id": build_dataset_id(checksum), "checksum": checksum}
    )

