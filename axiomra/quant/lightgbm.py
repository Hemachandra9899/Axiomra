"""LightGBM quant model.

LightGBM is optional at runtime. If it is not installed the model cannot be
constructed, which fails loudly rather than silently degrading.
"""

from __future__ import annotations

from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import QuantPrediction
from axiomra.quant.base import QuantModel
from axiomra.versions import MODEL_VERSION_LIGHTGBM

try:  # pragma: no cover - exercised only when lightgbm is present
    import lightgbm as lgbm
except ImportError:  # pragma: no cover
    lgbm = None  # type: ignore[assignment]

DEFAULT_FEATURES = [
    "momentum_5d",
    "momentum_20d",
    "momentum_60d",
    "volatility_20d",
    "volume_ratio",
    "distance_ema20",
]


class LightGBMQuantModel(QuantModel):
    """Wraps a trained LightGBM booster with an Axiomra-compatible contract."""

    name = "lightgbm"
    version = "v1"

    def __init__(
        self,
        model,
        features: list[str] | None = None,
        confidence: float = 0.75,
        model_version: str = MODEL_VERSION_LIGHTGBM,
    ) -> None:
        if lgbm is None:
            raise ImportError(
                "LightGBMQuantModel requires the 'lightgbm' package. "
                "Install Axiomra with: pip install 'axiomra[ml]'"
            )
        self._model = model
        self._features = features or DEFAULT_FEATURES
        self._confidence = confidence
        self.version = model_version

    async def predict(self, snapshot: MarketSnapshot) -> QuantPrediction:
        missing = set(self._features) - set(snapshot.features)
        if missing:
            raise ValueError(f"LightGBMQuantModel missing features: {sorted(missing)}")

        x = [[snapshot.features[name] for name in self._features]]
        score = float(self._model.predict(x)[0])

        return QuantPrediction(
            source="quant_lightgbm",
            symbol=snapshot.symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=self._confidence,
            expected_return=None,
            model_name=self.name,
            model_version=self.version,
        )
