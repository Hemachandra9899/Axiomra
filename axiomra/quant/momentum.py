"""Momentum baseline — the first, dependency-free quant model.

Used to validate the full pipeline before any ML training is introduced.
"""

from __future__ import annotations

from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import QuantPrediction
from axiomra.quant.base import QuantModel


class MomentumBaseline(QuantModel):
    """Scores a snapshot from momentum + trend + volatility features.

    The sign of the signal comes from 20-day momentum and distance from the
    20-day EMA; volatility and volume act as quality filters on confidence.
    """

    name = "momentum"
    version = "v1"

    async def predict(self, snapshot: MarketSnapshot) -> QuantPrediction:
        f = snapshot.features
        required = {"momentum_20d", "distance_ema20", "volatility_20d"}
        missing = required - set(f)
        if missing:
            raise ValueError(f"MomentumBaseline missing features: {sorted(missing)}")

        momentum = f.get("momentum_20d", 0.0)
        trend = f.get("distance_ema20", 0.0)
        vol = f.get("volatility_20d", 0.02)
        volume_ratio = f.get("volume_ratio", 1.0)

        raw = 0.6 * _clamp(momentum * 8.0) + 0.4 * _clamp(trend * 6.0)

        base_conf = 0.55
        if volume_ratio >= 1.0:
            base_conf += 0.10
        if vol > 0.0 and vol < 0.04:
            base_conf += 0.10
        elif vol >= 0.06:
            base_conf -= 0.15

        return QuantPrediction(
            source=f"quant_{self.name}",
            symbol=snapshot.symbol,
            score=_clamp(raw),
            confidence=min(1.0, max(0.0, base_conf)),
            expected_return=momentum,
            model_name=self.name,
            model_version=self.version,
            reasons=[
                f"momentum_20d={momentum:+.4f}",
                f"distance_ema20={trend:+.4f}",
            ],
        )


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
