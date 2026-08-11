"""Immutable decision journal.

A journal entry captures the full state behind one decision: data version,
model versions, prompts, risk policy, and outcome — so it can be audited and
reproduced later. Entries are never updated in place.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JournalEntry(BaseModel):
    """One immutable decision record."""

    decision_id: str
    symbol: str
    timestamp: datetime

    data_version: str
    feature_version: str
    model_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    risk_policy_version: str = ""

    regime: str = ""
    combined_score: float = 0.0
    confidence: float = 0.0
    proposed_action: str = ""

    risk_status: str = ""
    risk_reasons: list[str] = Field(default_factory=list)

    evidence: list[dict[str, Any]] = Field(default_factory=list)
    outcome_return_pct: float | None = None


class MemoryJournal:
    """Appends journal entries and exposes query helpers.

    The durable store (Postgres) lives behind the DataRepository; this class
    is the in-process write-behind and read model for the decision stream.
    """

    def __init__(self) -> None:
        self._entries: list[JournalEntry] = []

    def record(self, entry: JournalEntry) -> str:
        self._entries.append(entry)
        return entry.decision_id

    def get(self, decision_id: str) -> JournalEntry | None:
        for entry in reversed(self._entries):
            if entry.decision_id == decision_id:
                return entry
        return None

    def count(self) -> int:
        return len(self._entries)
