"""Shared domain validation helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Force a datetime to timezone-aware UTC, rejecting naive input."""
    if value.tzinfo is None:
        raise ValueError(f"naive datetime not allowed: {value}")
    return value.astimezone(UTC)
