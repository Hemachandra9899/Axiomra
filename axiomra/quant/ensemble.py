"""Weighted averaging of quant scores.

Prediction list is [(score, weight), ...]. Weights are normalized so the
result is a convex combination.
"""

from __future__ import annotations


def ensemble_quant(predictions: list[tuple[float, float]]) -> float:
    """Return the weighted average of (score, weight) pairs.

    Raises ValueError if total weight is not positive.
    """
    total_weight = sum(w for _, w in predictions)

    if total_weight <= 0:
        raise ValueError("ensemble_quant requires positive total weight")

    return sum(score * weight for score, weight in predictions) / total_weight
