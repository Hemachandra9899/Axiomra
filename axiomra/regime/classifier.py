"""Deterministic market regime classification.

Starts rule-based; later a probabilistic classifier can replace the internals
without changing the public contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from axiomra.domain.signals import Regime


def classify_regime(
    index_close: float,
    ma50: float,
    ma200: float,
    volatility: float,
) -> str:
    """Classify the market regime from index state.

    volatility is annualized or normalized realized volatility; 0.35 is the
    high-vol threshold for the V1 rule set.
    """
    if volatility > 0.35:
        return Regime.HIGH_VOL

    if index_close > ma50 > ma200:
        return Regime.TREND_UP

    if index_close < ma50 < ma200:
        return Regime.TREND_DOWN

    return Regime.RANGE


@dataclass
class RegimeClassifier:
    """Stateless classifier bound to its thresholds."""

    high_vol_threshold: float = 0.35

    def classify(
        self,
        index_close: float,
        ma50: float,
        ma200: float,
        volatility: float,
    ) -> str:
        if volatility > self.high_vol_threshold:
            return Regime.HIGH_VOL
        if index_close > ma50 > ma200:
            return Regime.TREND_UP
        if index_close < ma50 < ma200:
            return Regime.TREND_DOWN
        return Regime.RANGE
