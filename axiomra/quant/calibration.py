"""Score calibration.

A model score of 0.80 does not inherently mean "80% chance of profit".
Calibration maps raw scores to empirical outcome buckets so confidence is
evidence-based rather than invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CalibrationBucket:
    lo: float
    hi: float
    count: int = 0
    mean_return: float = 0.0
    median_return: float = 0.0
    win_rate: float = 0.0


@dataclass
class CalibrationTable:
    """Bucketed empirical returns per score range."""

    buckets: list[CalibrationBucket] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        scores: list[float],
        returns: list[float],
        edges: list[float] | None = None,
    ) -> CalibrationTable:
        if len(scores) != len(returns):
            raise ValueError("scores and returns must have equal length")
        if len(scores) == 0:
            return cls()

        edges = edges or [-1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0]
        arr = np.asarray(scores, dtype=float)
        ret = np.asarray(returns, dtype=float)

        buckets: list[CalibrationBucket] = []
        for lo, hi in zip(edges, edges[1:]):
            mask = (arr >= lo) & (arr < hi) if hi < edges[-1] else (arr >= lo) & (arr <= hi)
            n = int(mask.sum())
            bucket = CalibrationBucket(lo=lo, hi=hi, count=n)
            if n > 0:
                bucket.mean_return = float(ret[mask].mean())
                bucket.median_return = float(np.median(ret[mask]))
                bucket.win_rate = float((ret[mask] > 0).mean())
            buckets.append(bucket)

        return cls(buckets=buckets)

    def lookup(self, score: float) -> CalibrationBucket | None:
        for bucket in self.buckets:
            if bucket.lo <= score < bucket.hi or (
                bucket.hi == 1.0 and score == 1.0
            ):
                return bucket
        return None


class Calibrator:
    """Maps a raw score to empirical expected return."""

    def __init__(self, table: CalibrationTable) -> None:
        self.table = table

    @classmethod
    def from_samples(
        cls,
        scores: list[float],
        returns: list[float],
    ) -> Calibrator:
        return cls(CalibrationTable.build(scores, returns))

    def expected_return(self, score: float) -> float:
        bucket = self.table.lookup(score)
        if bucket is None or bucket.count == 0:
            return 0.0
        return bucket.mean_return
