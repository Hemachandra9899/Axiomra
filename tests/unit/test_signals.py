"""Signal classification: large no-trade region."""

from __future__ import annotations

from axiomra.domain.signals import classify_signal


def test_no_trade_region():
    assert classify_signal(0.29).label == "NO_TRADE"
    assert classify_signal(-0.29).label == "NO_TRADE"
    assert classify_signal(0.0).label == "NO_TRADE"


def test_long_thresholds():
    assert classify_signal(0.30).label == "LONG"
    assert classify_signal(0.59).label == "LONG"
    assert classify_signal(0.60).label == "STRONG_LONG"


def test_short_thresholds():
    assert classify_signal(-0.30).label == "SHORT"
    assert classify_signal(-0.60).label == "STRONG_SHORT"


def test_direction_mapping():
    assert classify_signal(0.7).direction == "LONG"
    assert classify_signal(-0.7).direction == "SHORT"
    assert classify_signal(0.0).direction == "NEUTRAL"
