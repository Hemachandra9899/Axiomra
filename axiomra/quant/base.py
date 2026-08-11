"""Quant model contract.

A quant model produces a forecast for one symbol. It never decides
quantities, never touches a broker, and returns structured predictions.
Qlib, LightGBM, XGBoost and transformer models all implement this contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from axiomra.domain.market import MarketSnapshot
from axiomra.domain.signals import QuantPrediction


class QuantModel(ABC):
    """Abstract forecast model."""

    name: str = "base"
    version: str = "v0"

    @abstractmethod
    async def predict(self, snapshot: MarketSnapshot) -> QuantPrediction: ...

    def model_versions(self) -> dict[str, str]:
        return {"quant_model": self.name, "quant_version": self.version}


@dataclass
class QuantEnsemble:
    """Weighted blend of quant models.

    weights: model name -> weight. Models not present default to 1.0 and
    the total is renormalized, so an entry with weight 0 disables it.
    """

    models: list[QuantModel]
    weights: dict[str, float] = field(default_factory=dict)

    async def predict(self, snapshot: MarketSnapshot) -> QuantPrediction:
        predictions = [await model.predict(snapshot) for model in self.models]
        if not predictions:
            raise ValueError("QuantEnsemble requires at least one model")

        weight_sum = 0.0
        weighted = 0.0
        for pred in predictions:
            w = self.weights.get(pred.model_name, 1.0)
            if w <= 0:
                continue
            weight_sum += w
            weighted += pred.score * w

        if weight_sum <= 0:
            raise ValueError("All ensemble weights are zero")

        fused = weighted / weight_sum
        confidence = min(1.0, sum(p.confidence for p in predictions) / len(predictions))

        return QuantPrediction(
            source="quant_ensemble",
            symbol=snapshot.symbol,
            score=fused,
            confidence=confidence,
            expected_return=sum(
                p.expected_return * self.weights.get(p.model_name, 1.0)
                for p in predictions
                if p.expected_return is not None
            )
            / weight_sum
            if any(p.expected_return is not None for p in predictions)
            else None,
            model_name="quant_ensemble",
            model_version="ensemble-v1",
            reasons=[f"{p.model_name}:{p.score:+.2f}" for p in predictions],
        )
