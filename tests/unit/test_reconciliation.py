"""Unit tests for Provider Reconciliation and Quarantine Engine."""

from __future__ import annotations

from datetime import UTC, datetime

from axiomra.data.reconciliation import ProviderReconciler, ReconciliationConfig
from axiomra.domain.market import Bar


def test_reconciliation_pass_clean_bars():
    """Matching bars from Upstox and NSE must result in PASS status."""
    dt = datetime(2024, 1, 2, tzinfo=UTC)
    u_bars = [Bar(symbol="RELIANCE.NS", timestamp=dt, open=2500.0, high=2550.0, low=2490.0, close=2540.0, volume=1000000.0)]
    n_bars = [Bar(symbol="RELIANCE.NS", timestamp=dt, open=2500.0, high=2550.0, low=2490.0, close=2540.0, volume=1000000.0)]

    reconciler = ProviderReconciler(ReconciliationConfig(max_close_diff_bps=10.0, max_volume_diff_pct=5.0))
    report = reconciler.reconcile_symbol_series("RELIANCE.NS", u_bars, n_bars)

    assert report.valid is True
    assert report.total_checked == 1
    assert report.passed_count == 1
    assert report.quarantined_count == 0
    assert report.items[0].status == "PASS"


def test_reconciliation_quarantine_on_price_discrepancy():
    """Close price difference > 10 bps must trigger QUARANTINE."""
    dt = datetime(2024, 1, 2, tzinfo=UTC)
    # 2540.0 vs 2550.0 -> diff ~ 39.3 bps > 10 bps threshold
    u_bars = [Bar(symbol="RELIANCE.NS", timestamp=dt, open=2500.0, high=2550.0, low=2490.0, close=2540.0, volume=1000000.0)]
    n_bars = [Bar(symbol="RELIANCE.NS", timestamp=dt, open=2500.0, high=2550.0, low=2490.0, close=2550.0, volume=1000000.0)]

    reconciler = ProviderReconciler(ReconciliationConfig(max_close_diff_bps=10.0, max_volume_diff_pct=5.0))
    report = reconciler.reconcile_symbol_series("RELIANCE.NS", u_bars, n_bars)

    assert report.valid is False
    assert report.quarantined_count == 1
    assert report.quarantined_items[0].status == "QUARANTINE"
    assert "close diff" in str(report.quarantined_items[0].note)


def test_reconciliation_missing_dates_flagged():
    """Missing dates in one provider feed must be recorded in missing_dates."""
    dt1 = datetime(2024, 1, 2, tzinfo=UTC)
    dt2 = datetime(2024, 1, 3, tzinfo=UTC)

    u_bars = [Bar(symbol="RELIANCE.NS", timestamp=dt1, open=2500.0, high=2550.0, low=2490.0, close=2540.0, volume=1000000.0)]
    n_bars = [
        Bar(symbol="RELIANCE.NS", timestamp=dt1, open=2500.0, high=2550.0, low=2490.0, close=2540.0, volume=1000000.0),
        Bar(symbol="RELIANCE.NS", timestamp=dt2, open=2540.0, high=2560.0, low=2520.0, close=2550.0, volume=1200000.0),
    ]

    reconciler = ProviderReconciler(ReconciliationConfig(fail_on_missing=True))
    report = reconciler.reconcile_symbol_series("RELIANCE.NS", u_bars, n_bars)

    assert len(report.missing_dates) == 1
    assert report.missing_dates[0]["missing_provider"] == "upstox"
    assert report.valid is False  # fail_on_missing=True marks report invalid
