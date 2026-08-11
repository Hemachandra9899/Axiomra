"""Daily long-only portfolio backtester.

Consumes a DataFrame of out-of-sample (walk-forward) prediction scores
and simulates a daily rebalanced, top-quintile long-only portfolio.

Key mechanics
─────────────
* Each trading day: rank stocks by score, build equal-weight target
  allocation over the top `top_fraction`, capped at `max_position_weight`.
* Transaction cost is charged on both sides of every trade:
  cost = sum(|new_w - old_w|) * cost_bps / 10_000
* Benchmark = equal-weight of all universe symbols available on that day
  (data-self-contained, no external index dependency).
* Sharpe uses annualised excess return over the benchmark.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from axiomra.data.snapshot import DatasetSnapshot


class BacktestConfig(BaseModel):
    """Configuration for a portfolio backtest run."""

    top_fraction: float = 0.2
    """Fraction of universe to hold long (top-quintile = 0.20)."""

    cost_bps: float = 10.0
    """One-way transaction cost in basis points."""

    max_position_weight: float = 0.10
    """Maximum single-stock weight after equal-weight distribution."""

    initial_capital: float = 1_000_000.0
    """Starting capital (informational only; returns are in fractions)."""


class DailyReturn(BaseModel):
    """Per-day portfolio and benchmark returns."""

    date: date
    portfolio_return: float
    benchmark_return: float
    n_positions: int
    turnover: float
    """Sum of absolute weight changes on this day (before cost application)."""


class BacktestReport(BaseModel):
    """Aggregate statistics from a completed backtest."""

    config: BacktestConfig
    dataset_id: str
    daily_returns: list[DailyReturn] = Field(default_factory=list)
    total_return: float = 0.0
    annualized_return: float = 0.0
    annualized_vol: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    calmar: float = 0.0
    avg_turnover: float = 0.0
    hit_rate: float = 0.0
    """Fraction of days where portfolio_return > benchmark_return."""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

_TRADING_DAYS = 252


def _build_return_matrix(snapshot: DatasetSnapshot) -> pd.DataFrame:
    """One-day forward returns for every symbol × date in the snapshot."""
    rows: list[dict] = []
    for symbol, bars in snapshot.bars.items():
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        for i in range(len(sorted_bars) - 1):
            b0 = sorted_bars[i]
            b1 = sorted_bars[i + 1]
            fwd_ret = (b1.close - b0.close) / b0.close if b0.close != 0 else float("nan")
            rows.append(
                {
                    "date": b0.timestamp.date(),
                    "symbol": symbol,
                    "fwd_return": fwd_ret,
                }
            )
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "fwd_return"])
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


def _equity_curve_stats(
    excess_rets: np.ndarray,
) -> tuple[float, float, float, float, float]:
    """(total_return, ann_return, ann_vol, sharpe, max_drawdown)."""
    if len(excess_rets) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    mean_daily = float(np.mean(excess_rets))
    std_daily = float(np.std(excess_rets, ddof=1)) if len(excess_rets) > 1 else 0.0

    ann_return = (1.0 + mean_daily) ** _TRADING_DAYS - 1.0
    ann_vol = std_daily * np.sqrt(_TRADING_DAYS)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

    # Max draw-down on cumulative portfolio (not excess) returns
    cumulative = np.cumprod(1.0 + excess_rets)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - running_max) / running_max
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) else 0.0

    total_return = float(cumulative[-1] - 1.0) if len(cumulative) else 0.0

    return total_return, ann_return, ann_vol, sharpe, max_drawdown


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def run_backtest(
    snapshot: DatasetSnapshot,
    predictions_df: pd.DataFrame,
    config: BacktestConfig | None = None,
) -> BacktestReport:
    """Run a daily long-only portfolio backtest.

    Parameters
    ----------
    snapshot:
        The DatasetSnapshot (provides forward returns from close prices).
    predictions_df:
        DataFrame with columns ``date`` (date or datetime), ``symbol`` (str),
        ``score`` (float). Usually the concatenated test-fold predictions from
        ``run_walk_forward``.
    config:
        Backtest configuration.  Defaults to ``BacktestConfig()``.

    Returns
    -------
    BacktestReport
    """
    if config is None:
        config = BacktestConfig()

    if predictions_df.empty:
        raise ValueError("predictions_df is empty — nothing to backtest")

    required_cols = {"date", "symbol", "score"}
    missing = required_cols - set(predictions_df.columns)
    if missing:
        raise ValueError(f"predictions_df missing columns: {missing}")

    # Normalise date column
    pred_df = predictions_df.copy()
    if not isinstance(pred_df["date"].iloc[0], date) or isinstance(pred_df["date"].iloc[0], datetime):
        pred_df["date"] = pd.to_datetime(pred_df["date"]).dt.date

    # Build forward-return matrix from snapshot bars
    ret_matrix = _build_return_matrix(snapshot)
    if ret_matrix.empty:
        raise ValueError("snapshot contains no bars — cannot compute returns")

    # Merge predictions with forward returns
    if not isinstance(ret_matrix["date"].iloc[0], date):
        ret_matrix["date"] = pd.to_datetime(ret_matrix["date"]).dt.date

    merged = pred_df.merge(ret_matrix, on=["date", "symbol"], how="inner")
    if merged.empty:
        raise ValueError(
            "No overlap between prediction dates/symbols and snapshot bars. "
            "Ensure predictions_df symbols and dates match the snapshot."
        )

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

        # Transaction cost on traded notional (one-way cost_bps on each side)
        cost = turnover * config.cost_bps / 10_000.0

        # Portfolio gross return = weighted sum of forward returns
        gross_port_ret = 0.0
        for sym, w in target_weights.items():
            fwd_ret = day_df.loc[sym, "fwd_return"] if sym in day_df.index else 0.0
            gross_port_ret += w * fwd_ret

        # Scale down by (1 - total_weight) to account for unfilled cap gaps
        total_w = sum(target_weights.values())
        if total_w < 1.0:
            gross_port_ret = gross_port_ret  # cash earns 0

        net_port_ret = gross_port_ret - cost

        # Benchmark = equal-weight of all symbols available this day
        all_day_syms = ret_matrix[ret_matrix["date"] == dt]["symbol"].tolist()
        bm_ret = (
            float(ret_matrix[ret_matrix["date"] == dt]["fwd_return"].mean())
            if all_day_syms
            else 0.0
        )

        daily_records.append(
            DailyReturn(
                date=dt,
                portfolio_return=net_port_ret,
                benchmark_return=bm_ret,
                n_positions=len(target_weights),
                turnover=turnover,
            )
        )

        prev_weights = dict(target_weights)

    if not daily_records:
        raise ValueError("Backtest produced no daily return records")

    port_rets = np.array([d.portfolio_return for d in daily_records], dtype=float)
    bm_rets = np.array([d.benchmark_return for d in daily_records], dtype=float)
    excess_rets = port_rets - bm_rets

    total_ret, ann_ret, ann_vol, sharpe, max_dd = _equity_curve_stats(excess_rets)

    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0.0
    avg_turnover = float(np.mean([d.turnover for d in daily_records]))
    hit_rate = float(np.mean(port_rets > bm_rets))

    return BacktestReport(
        config=config,
        dataset_id=snapshot.dataset_id,
        daily_returns=daily_records,
        total_return=total_ret,
        annualized_return=ann_ret,
        annualized_vol=ann_vol,
        sharpe=sharpe,
        max_drawdown=max_dd,
        calmar=calmar,
        avg_turnover=avg_turnover,
        hit_rate=hit_rate,
    )
