"""Trusted Baseline Report — persisted, checksummed research snapshots.

A ``BaselineReport`` binds a specific dataset (via ``dataset_id`` +
``dataset_checksum``), a model version, the walk-forward IC statistics,
and portfolio backtest metrics into a single immutable JSON artifact.

Use ``compare()`` to detect regressions between two baseline runs.

Storage layout (via ArtifactStore)::

    baselines/{model_version}/{dataset_id}/baseline.json
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from axiomra.backtest.backtester import BacktestReport
from axiomra.backtest.walkforward import WalkForwardReport
from axiomra.storage.base import ArtifactStore
from axiomra.storage.local import LocalArtifactStore


def _get_git_commit() -> str | None:
    """Best-effort: return the current HEAD short SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


class RegressionDelta(BaseModel):
    """Relative % change for a single metric: positive = improvement."""

    metric: str
    baseline_value: float
    candidate_value: float
    pct_change: float
    regressed: bool
    """True if the change is a meaningful degradation (>= 5% relative drop)."""


class CompareResult(BaseModel):
    """Structured comparison between two BaselineReports."""

    baseline_model_version: str
    candidate_model_version: str
    baseline_dataset_id: str
    candidate_dataset_id: str
    deltas: list[RegressionDelta] = Field(default_factory=list)
    any_regression: bool = False


class BaselineReport(BaseModel):
    """Immutable research baseline — walk-forward + backtest + provenance."""

    model_config = {"frozen": True}

    model_version: str
    dataset_id: str
    dataset_checksum: str
    walk_forward_report: WalkForwardReport
    backtest_report: BacktestReport
    created_at: datetime
    git_commit: str | None = None

    # ── Key summary metrics (extracted for fast compare without unpacking) ──
    mean_ic: float = 0.0
    mean_rank_ic: float = 0.0
    mean_ic_ir: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    annualized_return: float = 0.0
    avg_turnover: float = 0.0

    def compare(self, candidate: BaselineReport) -> CompareResult:
        """Compare *self* (baseline) against *candidate*.

        Returns ``CompareResult`` with per-metric deltas.  A metric is
        flagged as regressed when the candidate's value is more than 5%
        relatively worse than the baseline.

        For IC / Sharpe / return, *higher is better*.
        For max_drawdown, *less negative is better* (|MDD| should decrease).
        For avg_turnover, *lower is better*.
        """
        _HIGHER_IS_BETTER = ["mean_ic", "mean_rank_ic", "mean_ic_ir", "sharpe", "annualized_return"]
        _LOWER_IS_BETTER = ["avg_turnover"]
        _LESS_NEGATIVE_IS_BETTER = ["max_drawdown"]

        def _pct(b: float, c: float) -> float:
            if b == 0:
                return 0.0
            return (c - b) / abs(b)

        THRESHOLD = 0.05  # 5% relative degradation threshold

        deltas: list[RegressionDelta] = []

        for metric in _HIGHER_IS_BETTER:
            bv = getattr(self, metric)
            cv = getattr(candidate, metric)
            pct = _pct(bv, cv)
            regressed = pct < -THRESHOLD
            deltas.append(RegressionDelta(metric=metric, baseline_value=bv, candidate_value=cv, pct_change=pct, regressed=regressed))

        for metric in _LOWER_IS_BETTER:
            bv = getattr(self, metric)
            cv = getattr(candidate, metric)
            pct = _pct(bv, cv)
            # For lower-is-better: regressed when candidate is >5% higher
            regressed = pct > THRESHOLD
            deltas.append(RegressionDelta(metric=metric, baseline_value=bv, candidate_value=cv, pct_change=pct, regressed=regressed))

        for metric in _LESS_NEGATIVE_IS_BETTER:
            bv = getattr(self, metric)
            cv = getattr(candidate, metric)
            # max_drawdown is negative; regressed = drawdown got larger in magnitude
            pct = _pct(abs(bv), abs(cv)) if bv != 0 else 0.0
            regressed = cv < bv - THRESHOLD * abs(bv)
            deltas.append(RegressionDelta(metric=metric, baseline_value=bv, candidate_value=cv, pct_change=pct, regressed=regressed))

        return CompareResult(
            baseline_model_version=self.model_version,
            candidate_model_version=candidate.model_version,
            baseline_dataset_id=self.dataset_id,
            candidate_dataset_id=candidate.dataset_id,
            deltas=deltas,
            any_regression=any(d.regressed for d in deltas),
        )


def create_baseline(
    model_version: str,
    dataset_id: str,
    dataset_checksum: str,
    walk_forward_report: WalkForwardReport,
    backtest_report: BacktestReport,
    git_commit: str | None = None,
) -> BaselineReport:
    """Construct a ``BaselineReport`` from component reports."""
    if git_commit is None:
        git_commit = _get_git_commit()

    return BaselineReport(
        model_version=model_version,
        dataset_id=dataset_id,
        dataset_checksum=dataset_checksum,
        walk_forward_report=walk_forward_report,
        backtest_report=backtest_report,
        created_at=datetime.now(UTC),
        git_commit=git_commit,
        # Summary mirrors
        mean_ic=walk_forward_report.mean_ic,
        mean_rank_ic=walk_forward_report.mean_rank_ic,
        mean_ic_ir=walk_forward_report.mean_ic_ir,
        sharpe=backtest_report.sharpe,
        max_drawdown=backtest_report.max_drawdown,
        annualized_return=backtest_report.annualized_return,
        avg_turnover=backtest_report.avg_turnover,
    )


def _baseline_key(model_version: str, dataset_id: str) -> str:
    return f"baselines/{model_version}/{dataset_id}/baseline.json"


def save_baseline(
    baseline: BaselineReport,
    store: ArtifactStore | None = None,
) -> str:
    """Persist baseline JSON artifact.  Returns the artifact key."""
    store = store or LocalArtifactStore()
    key = _baseline_key(baseline.model_version, baseline.dataset_id)
    payload = baseline.model_dump_json(indent=2).encode("utf-8")
    store.put_bytes(key, payload)
    return key


def load_baseline(
    model_version: str,
    dataset_id: str,
    store: ArtifactStore | None = None,
) -> BaselineReport:
    """Load a persisted baseline by model_version + dataset_id."""
    store = store or LocalArtifactStore()
    key = _baseline_key(model_version, dataset_id)
    if not store.exists(key):
        raise FileNotFoundError(f"Baseline not found: {key}")
    data = json.loads(store.get_bytes(key).decode("utf-8"))
    return BaselineReport.model_validate(data)
