"""Data quality validation suite.

Validates point-in-time market snapshots before feature computation and model training:
1. Non-empty dataset check (symbols > 0 and bars > 0).
2. OHLC sanity checks (positive prices, High >= Open/Close, Low <= Open/Close).
3. Price outlier detection (single-day price jumps exceeding max threshold).
4. Bar gap detection (unexplained calendar gaps between consecutive bars).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from axiomra.data.snapshot import DatasetSnapshot


class DataQualityCheckResult(BaseModel):
    rule_name: str
    passed: bool
    issues: list[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    valid: bool
    total_symbols: int
    total_bars: int
    checks: list[DataQualityCheckResult] = Field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return sum(len(c.issues) for c in self.checks)


class DataQualityChecker:
    """Automated data quality checker over DatasetSnapshot instances."""

    def __init__(
        self,
        max_jump_pct: float = 0.50,
        max_gap_days: int = 7,
    ) -> None:
        self.max_jump_pct = max_jump_pct
        self.max_gap_days = max_gap_days

    def check(self, snapshot: DatasetSnapshot) -> DataQualityReport:
        checks: list[DataQualityCheckResult] = []

        empty_issues: list[str] = []
        ohlc_issues: list[str] = []
        outlier_issues: list[str] = []
        gap_issues: list[str] = []

        total_bars = 0
        total_symbols = len(snapshot.bars)

        if total_symbols == 0:
            empty_issues.append("Empty dataset: total_symbols is 0")

        for symbol, bars in snapshot.bars.items():
            total_bars += len(bars)

            for i, bar in enumerate(bars):
                # OHLC Bounds check
                if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
                    ohlc_issues.append(f"{symbol} at {bar.timestamp}: non-positive price in OHLC")
                if bar.high < max(bar.open, bar.close):
                    ohlc_issues.append(
                        f"{symbol} at {bar.timestamp}: High ({bar.high}) < max(Open, Close)"
                    )
                if bar.low > min(bar.open, bar.close):
                    ohlc_issues.append(
                        f"{symbol} at {bar.timestamp}: Low ({bar.low}) > min(Open, Close)"
                    )
                if bar.volume < 0:
                    ohlc_issues.append(f"{symbol} at {bar.timestamp}: negative volume ({bar.volume})")

                # Single-day price jump outlier check
                if i > 0:
                    prev_close = bars[i - 1].close
                    if prev_close > 0:
                        ret = abs(bar.close / prev_close - 1.0)
                        if ret > self.max_jump_pct:
                            outlier_issues.append(
                                f"{symbol} at {bar.timestamp}: price jump {ret:.2%} exceeds {self.max_jump_pct:.0%}"
                            )

                    # Gap check
                    gap = (bar.timestamp - bars[i - 1].timestamp).days
                    if gap > self.max_gap_days:
                        gap_issues.append(
                            f"{symbol}: gap of {gap} days between {bars[i - 1].timestamp.date()} and {bar.timestamp.date()}"
                        )

        if total_bars == 0:
            empty_issues.append("Empty dataset: total_bars is 0")

        checks.append(
            DataQualityCheckResult(
                rule_name="non_empty",
                passed=len(empty_issues) == 0,
                issues=empty_issues,
            )
        )
        checks.append(
            DataQualityCheckResult(
                rule_name="ohlc_bounds",
                passed=len(ohlc_issues) == 0,
                issues=ohlc_issues,
            )
        )
        checks.append(
            DataQualityCheckResult(
                rule_name="price_outliers",
                passed=len(outlier_issues) == 0,
                issues=outlier_issues,
            )
        )
        checks.append(
            DataQualityCheckResult(
                rule_name="bar_gaps",
                passed=len(gap_issues) == 0,
                issues=gap_issues,
            )
        )

        valid = all(c.passed for c in checks)

        return DataQualityReport(
            valid=valid,
            total_symbols=total_symbols,
            total_bars=total_bars,
            checks=checks,
        )
