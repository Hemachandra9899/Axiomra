"""Unit tests for DataQualityChecker rules."""

from __future__ import annotations

from datetime import UTC, datetime

from axiomra.data.quality import DataQualityChecker
from axiomra.data.snapshot import create_snapshot
from axiomra.data.universe import Universe


def test_quality_checker_empty_snapshot_fails():
    """DataQualityChecker must mark valid=False when checking an empty DatasetSnapshot."""
    snapshot = create_snapshot(
        universe=Universe(name="EMPTY", version="v1", as_of=datetime.now(UTC), members=[]),
        bars={},
        data_version="v1",
    )

    checker = DataQualityChecker()
    report = checker.check(snapshot)

    assert report.valid is False
    assert report.total_issues > 0
    non_empty_check = next(c for c in report.checks if c.rule_name == "non_empty")
    assert non_empty_check.passed is False
    assert "Empty dataset: total_symbols is 0" in non_empty_check.issues
