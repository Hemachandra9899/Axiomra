"""Daily long-only portfolio backtester — Research Integrity Edition.

Execution convention
────────────────────
Signal is known at T close. Earliest executable entry: open[T+1].
Default policy OPEN_NEXT:

    entry  = open[T+1]
    exit   = close[T+1]
    return = close[T+1] / open[T+1] − 1

This matches the execution-aligned target used in `build_training_frame()`.

Metrics
───────
Portfolio and benchmark equity curves are built and measured **independently**.
MDD, CAGR, Calmar, Sortino all come from the respective raw-return curve.
Relative stats (alpha, tracking error, IR) are derived from the spread.
"""

from __future__ import annotations

import subprocess
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from axiomra.data.snapshot import DatasetSnapshot

if TYPE_CHECKING:
    from axiomra.data.universe import IndexMembership

_TRADING_DAYS = 252


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


class ExecutionPolicy(StrEnum):
    """How predictions are converted to fills."""

    OPEN_NEXT = "open_next"
    """Entry at open[T+1], exit at close[T+1].  Correct execution timing."""

    CLOSE_NEXT = "close_next"
    """Entry at close[T], exit at close[T+1].  Naive / incorrect — for comparison only."""


class BacktestConfig(BaseModel):
    """Configuration for a portfolio backtest run."""

    top_fraction: float = 0.2
    """Fraction of universe to hold long (top-quintile = 0.20)."""

    cost_bps: float = 10.0
    """One-way transaction cost in basis points (cost_policy_version = simple-bps-v1)."""

    max_position_weight: float = 0.10
    """Maximum single-stock weight after equal-weight distribution."""

    initial_capital: float = 1_000_000.0
    """Starting capital (informational only; returns are in fractions)."""

    execution_policy: ExecutionPolicy = ExecutionPolicy.OPEN_NEXT
    """Execution convention used to map predictions to realised returns."""


# ─────────────────────────────────────────────────────────────────────────────
# Output models
# ─────────────────────────────────────────────────────────────────────────────


class DailyReturn(BaseModel):
    """Per-day portfolio and benchmark returns."""

    date: date
    portfolio_return: float
    benchmark_return: float
    n_positions: int
    turnover: float
    """Sum of absolute weight changes on this day (before cost application)."""


class CurveStats(BaseModel):
    """Statistics for one equity curve — portfolio OR benchmark."""

    total_return: float = 0.0
    cagr: float = 0.0
    annualized_vol: float = 0.0
    sharpe: float = 0.0
    """Annualised return / annualised vol (risk-free = 0)."""
    sortino: float = 0.0
    """Annualised return / annualised downside deviation."""
    max_drawdown: float = 0.0
    """Peak-to-trough drawdown from the actual curve (negative number)."""
    calmar: float = 0.0
    """CAGR / |max_drawdown|; 0 when MDD = 0."""


class RelativeStats(BaseModel):
    """Portfolio-vs-benchmark relative statistics."""

    excess_return: float = 0.0
    """Portfolio total_return − benchmark total_return."""
    tracking_error: float = 0.0
    """Annualised std of daily (portfolio_return − benchmark_return)."""
    information_ratio: float = 0.0
    """Annualised mean excess return / tracking error."""
    hit_rate: float = 0.0
    """Fraction of days where portfolio_return > benchmark_return."""


class BacktestReport(BaseModel):
    """Aggregate statistics from a completed backtest."""

    config: BacktestConfig
    dataset_id: str
    daily_returns: list[DailyReturn] = Field(default_factory=list)

    portfolio: CurveStats = Field(default_factory=CurveStats)
    """Statistics computed on the portfolio equity curve."""

    benchmark: CurveStats = Field(default_factory=CurveStats)
    """Statistics computed on the benchmark equity curve."""

    relative: RelativeStats = Field(default_factory=RelativeStats)
    """Portfolio-vs-benchmark relative statistics."""

    avg_turnover: float = 0.0

    # ── Provenance / lineage ─────────────────────────────────────────────────
    dataset_checksum: str = ""
    feature_version: str = ""
    model_version: str = ""
    target_version: str = "execution-aligned-v1"
    execution_policy_version: str = ""
    cost_policy_version: str = "simple-bps-v1"
    git_commit: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_git_commit() -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _build_execution_return_matrix(
    snapshot: DatasetSnapshot,
    policy: ExecutionPolicy,
) -> pd.DataFrame:
    """Build the per-symbol × per-date return matrix according to execution policy.

    OPEN_NEXT (correct):
        date T → return = close[T+1] / open[T+1] − 1
        Signal at T close, entry at T+1 open, exit at T+1 close.

    CLOSE_NEXT (naive/wrong — kept for test comparison only):
        date T → return = close[T+1] / close[T] − 1
    """
    rows: list[dict] = []
    for symbol, bars in snapshot.bars.items():
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        for i in range(len(sorted_bars) - 1):
            b0 = sorted_bars[i]
            b1 = sorted_bars[i + 1]
            if policy == ExecutionPolicy.OPEN_NEXT:
                fwd_ret = (b1.close - b1.open) / b1.open if b1.open != 0 else float("nan")
            else:  # CLOSE_NEXT — naive
                fwd_ret = (b1.close - b0.close) / b0.close if b0.close != 0 else float("nan")
            rows.append({
                "date": b0.timestamp.date(),
                "symbol": symbol,
                "open_next": float(b1.open),
                "fwd_return": fwd_ret,
            })
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "open_next", "fwd_return"])
    return pd.DataFrame(rows)


def _build_target_weights(
    scores: pd.Series,
    top_fraction: float,
    max_weight: float,
) -> dict[str, float]:
    """Equal-weight top-quintile allocation with per-stock cap."""
    if scores.empty:
        return {}
    k = max(1, int(round(len(scores) * top_fraction)))
    top_symbols = scores.nlargest(k).index.tolist()
    raw_weight = 1.0 / len(top_symbols)
    weight = min(raw_weight, max_weight)
    return {sym: weight for sym in top_symbols}


def _compute_sortino(rets: np.ndarray) -> float:
    """Annualised Sortino ratio (downside deviation only, risk-free = 0)."""
    if len(rets) < 2:
        return 0.0
    mean_daily = float(np.mean(rets))
    ann_return = (1.0 + mean_daily) ** _TRADING_DAYS - 1.0
    downside = rets[rets < 0]
    if len(downside) == 0:
        return 0.0
    downside_std = float(np.std(downside, ddof=1)) * np.sqrt(_TRADING_DAYS)
    return ann_return / downside_std if downside_std > 0 else 0.0


def _compute_curve_stats(rets: np.ndarray) -> CurveStats:
    """Compute CurveStats from a daily-return array (portfolio or benchmark)."""
    if len(rets) == 0:
        return CurveStats()

    mean_daily = float(np.mean(rets))
    std_daily = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0

    cagr = (1.0 + mean_daily) ** _TRADING_DAYS - 1.0
    ann_vol = std_daily * np.sqrt(_TRADING_DAYS)
    sharpe = cagr / ann_vol if ann_vol > 0 else 0.0
    sortino = _compute_sortino(rets)

    cum = np.cumprod(1.0 + rets)
    total_return = float(cum[-1] - 1.0)
    running_max = np.maximum.accumulate(cum)
    drawdowns = (cum - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) else 0.0
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else 0.0

    return CurveStats(
        total_return=total_return,
        cagr=cagr,
        annualized_vol=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=calmar,
    )


def _compute_relative_stats(port_rets: np.ndarray, bm_rets: np.ndarray) -> RelativeStats:
    """Compute relative statistics from two return arrays."""
    if len(port_rets) == 0:
        return RelativeStats()

    cum_port = float(np.prod(1.0 + port_rets)) - 1.0
    cum_bm = float(np.prod(1.0 + bm_rets)) - 1.0
    excess_return = cum_port - cum_bm

    daily_excess = port_rets - bm_rets
    tracking_error = float(np.std(daily_excess, ddof=1)) * np.sqrt(_TRADING_DAYS) if len(daily_excess) > 1 else 0.0
    mean_daily_excess = float(np.mean(daily_excess))
    ann_excess = (1.0 + mean_daily_excess) ** _TRADING_DAYS - 1.0
    information_ratio = ann_excess / tracking_error if tracking_error > 0 else 0.0
    hit_rate = float(np.mean(port_rets > bm_rets))

    return RelativeStats(
        excess_return=excess_return,
        tracking_error=tracking_error,
        information_ratio=information_ratio,
        hit_rate=hit_rate,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def run_backtest(
    snapshot: DatasetSnapshot,
    predictions_df: pd.DataFrame,
    config: BacktestConfig | None = None,
    memberships: list[IndexMembership] | None = None,
    dataset_checksum: str = "",
    feature_version: str = "",
    model_version: str = "",
    git_commit: str | None = None,
) -> BacktestReport:
    """Run a daily long-only portfolio backtest.

    Parameters
    ----------
    snapshot:
        The DatasetSnapshot (provides OHLCV bars for return computation).
    predictions_df:
        DataFrame with columns ``date``, ``symbol``, ``score``.
        Must contain only OOS predictions (e.g. from ``oos_predictions_df()``).
    config:
        Backtest configuration.  Defaults to ``BacktestConfig()``.
    memberships:
        Optional list of ``IndexMembership`` records.  When provided the
        benchmark is restricted to PIT-eligible members on each date.
    dataset_checksum / feature_version / model_version / git_commit:
        Provenance fields written into the returned ``BacktestReport``.
    """
    if config is None:
        config = BacktestConfig()

    if predictions_df.empty:
        raise ValueError("predictions_df is empty — nothing to backtest")

    required_cols = {"date", "symbol", "score"}
    missing = required_cols - set(predictions_df.columns)
    if missing:
        raise ValueError(f"predictions_df missing columns: {missing}")

    # Normalise date column to Python date objects
    pred_df = predictions_df.copy()
    if not isinstance(pred_df["date"].iloc[0], date) or isinstance(pred_df["date"].iloc[0], datetime):
        pred_df["date"] = pd.to_datetime(pred_df["date"]).dt.date

    # Build execution-aligned return matrix
    ret_matrix = _build_execution_return_matrix(snapshot, config.execution_policy)
    if ret_matrix.empty:
        raise ValueError("snapshot contains no bars — cannot compute returns")

    if not isinstance(ret_matrix["date"].iloc[0], date):
        ret_matrix["date"] = pd.to_datetime(ret_matrix["date"]).dt.date

    merged = pred_df.merge(ret_matrix, on=["date", "symbol"], how="inner")
    if merged.empty:
        raise ValueError(
            "No overlap between prediction dates/symbols and snapshot bars. "
            "Ensure predictions_df symbols and dates match the snapshot."
        )

    # Build PIT membership registry for benchmark filtering
    pit_registry = None
    if memberships:
        from axiomra.data.universe import HistoricalUniverseRegistry  # noqa: PLC0415
        pit_registry = HistoricalUniverseRegistry()
        for m in memberships:
            pit_registry.add_membership(m)

    trading_dates = sorted(merged["date"].unique())
    prev_weights: dict[str, float] = {}
    daily_records: list[DailyReturn] = []

    for dt in trading_dates:
        day_df = merged[merged["date"] == dt].set_index("symbol")
        if day_df.empty:
            continue

        # Target portfolio weights
        target_weights = _build_target_weights(
            day_df["score"],
            config.top_fraction,
            config.max_position_weight,
        )

        # Turnover = sum of absolute weight changes
        all_syms = set(prev_weights) | set(target_weights)
        turnover = sum(
            abs(target_weights.get(s, 0.0) - prev_weights.get(s, 0.0))
            for s in all_syms
        )

        # Transaction cost (one-way cost_bps on each unit of turnover)
        cost = turnover * config.cost_bps / 10_000.0

        # Portfolio gross return = weighted sum of execution-aligned returns
        gross_port_ret = sum(
            w * (day_df.loc[sym, "fwd_return"] if sym in day_df.index else 0.0)
            for sym, w in target_weights.items()
        )
        net_port_ret = gross_port_ret - cost

        # PIT benchmark — equal-weight of eligible members on this date
        dt_as_datetime = datetime(dt.year, dt.month, dt.day, tzinfo=__import__("datetime").timezone.utc)
        if pit_registry is not None:
            eligible_symbols = pit_registry.constituents_at(
                snapshot.universe.name, dt_as_datetime
            )
            bm_rows = ret_matrix[
                (ret_matrix["date"] == dt) & ret_matrix["symbol"].isin(eligible_symbols)
            ]
        else:
            bm_rows = ret_matrix[ret_matrix["date"] == dt]

        bm_ret = float(bm_rows["fwd_return"].mean()) if not bm_rows.empty else 0.0

        daily_records.append(DailyReturn(
            date=dt,
            portfolio_return=net_port_ret,
            benchmark_return=bm_ret,
            n_positions=len(target_weights),
            turnover=turnover,
        ))
        prev_weights = dict(target_weights)

    if not daily_records:
        raise ValueError("Backtest produced no daily return records")

    port_rets = np.array([d.portfolio_return for d in daily_records], dtype=float)
    bm_rets = np.array([d.benchmark_return for d in daily_records], dtype=float)

    # Compute stats independently on each curve
    portfolio_stats = _compute_curve_stats(port_rets)
    benchmark_stats = _compute_curve_stats(bm_rets)
    relative_stats = _compute_relative_stats(port_rets, bm_rets)
    avg_turnover = float(np.mean([d.turnover for d in daily_records]))

    return BacktestReport(
        config=config,
        dataset_id=snapshot.dataset_id,
        daily_returns=daily_records,
        portfolio=portfolio_stats,
        benchmark=benchmark_stats,
        relative=relative_stats,
        avg_turnover=avg_turnover,
        dataset_checksum=dataset_checksum,
        feature_version=feature_version,
        model_version=model_version,
        target_version="execution-aligned-v1",
        execution_policy_version=config.execution_policy.value,
        cost_policy_version="simple-bps-v1",
        git_commit=git_commit or _get_git_commit(),
    )
