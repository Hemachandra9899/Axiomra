"""Trusted Baseline Report — persisted, checksummed research snapshots.

A ``BaselineReport`` binds a specific dataset (via ``dataset_id`` +
``dataset_checksum``), a model version, the walk-forward IC statistics,
and portfolio backtest metrics into a single immutable JSON artifact.

Use ``compare()`` to detect regressions between two baseline runs.
Regression rules use **both** absolute and relative thresholds to avoid
false alarms on near-zero metrics (e.g. IC = 0.001 → 0.0008).

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
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Regression rules
# ─────────────────────────────────────────────────────────────────────────────


class RegressionRule(BaseModel):
    """Per-metric regression detection rule with dual absolute + relative thresholds.

    A metric is flagged as regressed only when the degradation exceeds
    **both** ``abs_tol`` AND (if set) ``rel_tol``.  This prevents noise-level
    IC values (e.g. 0.001 → 0.0008) from triggering false CI alarms.

    For Sharpe and MDD, only ``abs_tol`` applies (``rel_tol=None``).
    """

    metric: str
    abs_tol: float
    """Minimum absolute degradation required to flag as regression."""
    rel_tol: float | None = None
    """Minimum relative degradation (fraction) required to flag.  None = disabled."""
    higher_is_better: bool = True

    def is_regression(self, baseline_value: float, candidate_value: float) -> bool:
        delta = candidate_value - baseline_value
        if self.higher_is_better:
            degradation = -delta  # negative = improvement; positive = regression
        else:
            degradation = delta  # lower is better → increase = regression

        abs_breach = degradation >= self.abs_tol
        if self.rel_tol is not None and baseline_value != 0:
            rel_breach = (degradation / abs(baseline_value)) >= self.rel_tol
        else:
            rel_breach = True  # no relative rule — abs_tol alone decides

        return abs_breach and rel_breach


# Default rules applied when compare() is called without explicit rules
_DEFAULT_RULES: list[RegressionRule] = [
    RegressionRule(metric="mean_ic",           abs_tol=0.003, rel_tol=0.10, higher_is_better=True),
    RegressionRule(metric="mean_rank_ic",      abs_tol=0.003, rel_tol=0.10, higher_is_better=True),
    RegressionRule(metric="mean_ic_ir",        abs_tol=0.05,  rel_tol=0.10, higher_is_better=True),
    RegressionRule(metric="sharpe",            abs_tol=0.10,  rel_tol=None, higher_is_better=True),
    RegressionRule(metric="annualized_return", abs_tol=0.005, rel_tol=0.10, higher_is_better=True),
    RegressionRule(metric="max_drawdown",      abs_tol=0.02,  rel_tol=None, higher_is_better=False),
    RegressionRule(metric="avg_turnover",      abs_tol=0.05,  rel_tol=0.10, higher_is_better=False),
]


# ─────────────────────────────────────────────────────────────────────────────
# Output models
# ─────────────────────────────────────────────────────────────────────────────


class RegressionDelta(BaseModel):
    """Relative % change for a single metric: positive = improvement."""

    metric: str
    baseline_value: float
    candidate_value: float
    pct_change: float
    regressed: bool
    """True if the change is a meaningful degradation per the RegressionRule."""


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

    # ── Key summary metrics (extracted from portfolio.* for fast compare) ───
    mean_ic: float = 0.0
    mean_rank_ic: float = 0.0
    mean_ic_ir: float = 0.0
    sharpe: float = 0.0
    """Portfolio Sharpe ratio (from portfolio equity curve, not excess-return curve)."""
    max_drawdown: float = 0.0
    """Portfolio max drawdown (from portfolio equity curve)."""
    annualized_return: float = 0.0
    """Portfolio CAGR."""
    avg_turnover: float = 0.0

    def compare(
        self,
        candidate: BaselineReport,
        rules: list[RegressionRule] | None = None,
    ) -> CompareResult:
        """Compare *self* (baseline) against *candidate* using per-metric rules.

        Parameters
        ----------
        candidate:
            The newer run to evaluate.
        rules:
            Custom ``RegressionRule`` list.  Defaults to ``_DEFAULT_RULES``.

        Returns
        -------
        CompareResult with per-metric deltas and ``any_regression`` flag.
        """
        active_rules = rules if rules is not None else _DEFAULT_RULES

        def _pct(b: float, c: float) -> float:
            return (c - b) / abs(b) if b != 0 else 0.0

        deltas: list[RegressionDelta] = []
        for rule in active_rules:
            bv = getattr(self, rule.metric)
            cv = getattr(candidate, rule.metric)
            pct = _pct(bv, cv)
            regressed = rule.is_regression(bv, cv)
            deltas.append(RegressionDelta(
                metric=rule.metric,
                baseline_value=bv,
                candidate_value=cv,
                pct_change=pct,
                regressed=regressed,
            ))

        return CompareResult(
            baseline_model_version=self.model_version,
            candidate_model_version=candidate.model_version,
            baseline_dataset_id=self.dataset_id,
            candidate_dataset_id=candidate.dataset_id,
            deltas=deltas,
            any_regression=any(d.regressed for d in deltas),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Factory and persistence
# ─────────────────────────────────────────────────────────────────────────────


def create_baseline(
    model_version: str,
    dataset_id: str,
    dataset_checksum: str,
    walk_forward_report: WalkForwardReport,
    backtest_report: BacktestReport,
    git_commit: str | None = None,
) -> BaselineReport:
    """Construct a ``BaselineReport`` from component reports.

    Summary scalars are extracted from ``portfolio.*`` (not the excess-return
    curve) so they reflect actual portfolio performance.
    """
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
        # Summary mirrors from portfolio curve + walk-forward report
        mean_ic=walk_forward_report.mean_ic,
        mean_rank_ic=walk_forward_report.mean_rank_ic,
        mean_ic_ir=walk_forward_report.mean_ic_ir,
        sharpe=backtest_report.portfolio.sharpe,
        max_drawdown=backtest_report.portfolio.max_drawdown,
        annualized_return=backtest_report.portfolio.cagr,
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
