"""Walk-forward evaluation: split, train, test, report.

Expanding-window walk-forward is the only backtest the V1 research path uses.
Every model version is trained only on data that predates the test fold, so
the reported IC is a true out-of-sample statistic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd
from pydantic import BaseModel

from axiomra.data.snapshot import DatasetSnapshot
from axiomra.quant.trainer import build_training_frame


@dataclass
class WalkForwardSplitter:
    """Splits sorted dates into expanding-window (train, test) folds."""

    n_splits: int = 4
    min_train_days: int = 250

    def folds(
        self,
        dates: list[datetime],
    ) -> list[tuple[list[datetime], list[datetime]]]:
        """Yield (train_dates, test_dates) with a strictly growing train set."""
        ordered = sorted(set(dates))
        if len(ordered) < self.n_splits + 2:
            raise ValueError(
                f"need >= {self.n_splits + 2} distinct dates, got {len(ordered)}"
            )

        # Each test fold is ~1/n_splits of the timeline.
        cut = len(ordered) // self.n_splits
        result: list[tuple[list[datetime], list[datetime]]] = []
        for i in range(1, self.n_splits):
            split_at = cut * i
            train = ordered[:split_at]
            test = ordered[split_at : split_at + cut]
            if len(train) < self.min_train_days:
                raise ValueError(
                    f"train fold too short: {len(train)} days < {self.min_train_days}"
                )
            result.append((train, test))
        return result


class FoldReport(BaseModel):
    """Per-fold out-of-sample statistics."""

    fold: int
    train_start: datetime
    test_start: datetime
    test_end: datetime
    n_train: int
    n_test: int
    ic: float
    rank_ic: float
    hit_rate: float
    top_quintile_return: float
    n_traded: int = 0


class WalkForwardReport(BaseModel):
    """Aggregate over all folds."""

    folds: list[FoldReport] = field(default_factory=list)  # type: ignore[assignment]
    mean_ic: float = 0.0
    mean_rank_ic: float = 0.0
    mean_hit_rate: float = 0.0
    mean_top_quintile_return: float = 0.0

    @property
    def n_folds(self) -> int:
        return len(self.folds)


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2:
        return 0.0
    a_c = a - a.mean()
    b_c = b - b.mean()
    denom = np.sqrt((a_c**2).sum() * (b_c**2).sum())
    if denom == 0:
        return 0.0
    return float(np.dot(a_c, b_c) / denom)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2:
        return 0.0
    return _pearson(pd.Series(a).rank().values, pd.Series(b).rank().values)


def evaluate_predictions(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    top_fraction: float = 0.2,
) -> dict[str, float]:
    """IC, rank IC, hit rate, and top-quintile mean forward return."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = ~np.isnan(y_true)
    if valid.sum() < 2:
        return {"ic": 0.0, "rank_ic": 0.0, "hit_rate": 0.0, "top_quintile_return": 0.0}

    y_true = y_true[valid]
    y_pred = y_pred[valid]
    sign = np.sign(y_pred)
    hit = float(np.mean((y_true * sign) > 0)) if len(y_true) else 0.0

    k = max(1, int(round(len(y_pred) * top_fraction)))
    idx = np.argsort(y_pred)[::-1][:k]

    return {
        "ic": _pearson(y_true, y_pred),
        "rank_ic": _spearman(y_true, y_pred),
        "hit_rate": hit,
        "top_quintile_return": float(y_true[idx].mean()),
    }


def run_walk_forward(
    snapshot: DatasetSnapshot,
    horizon: int = 5,
    n_splits: int = 4,
    min_train_days: int = 250,
    estimator_factory: object | None = None,
) -> WalkForwardReport:
    """Walk-forward training and out-of-sample evaluation.

    `estimator_factory(X_train, y_train) -> model` must expose `.predict(X)`.
    Defaults to LightGBM when available.
    """
    if estimator_factory is None:
        import lightgbm as lgbm  # noqa: PLC0415

        from axiomra.quant.trainer import _default_lgbm_params  # noqa: PLC0415

        def default_factory(x, y):
            params = _default_lgbm_params()
            model = lgbm.LGBMRegressor(**params)
            model.fit(x, y)
            return model

        estimator_factory = default_factory

    frame = build_training_frame(snapshot, horizon=horizon)
    if frame.empty:
        raise ValueError("no training rows available")

    dates = sorted(frame["date"].unique())
    splitter = WalkForwardSplitter(n_splits=n_splits, min_train_days=min_train_days)
    folds = splitter.folds(dates)

    feature_cols = [
        c
        for c in frame.columns
        if c not in {"symbol", "date", "target"}
    ]

    fold_reports: list[FoldReport] = []
    for i, (train_dates, test_dates) in enumerate(folds, start=1):
        train = frame[frame["date"].isin(train_dates)]
        test = frame[frame["date"].isin(test_dates)]

        x_tr = train[feature_cols].to_numpy(dtype=float)
        y_tr = train["target"].to_numpy(dtype=float)
        x_te = test[feature_cols].to_numpy(dtype=float)
        y_te = test["target"].to_numpy(dtype=float)

        if len(x_tr) < 20 or len(x_te) < 2:
            continue

        model = estimator_factory(x_tr, y_tr)  # type: ignore[operator]
        preds = np.asarray(model.predict(x_te), dtype=float)
        metrics = evaluate_predictions(y_te, preds)

        fold_reports.append(
            FoldReport(
                fold=i,
                train_start=min(train_dates),
                test_start=min(test_dates),
                test_end=max(test_dates),
                n_train=len(x_tr),
                n_test=len(x_te),
                n_traded=int((preds > 0).sum()),
                **metrics,
            )
        )

    if not fold_reports:
        raise ValueError("walk-forward produced no valid folds")

    return WalkForwardReport(
        folds=fold_reports,
        mean_ic=float(np.mean([f.ic for f in fold_reports])),
        mean_rank_ic=float(np.mean([f.rank_ic for f in fold_reports])),
        mean_hit_rate=float(np.mean([f.hit_rate for f in fold_reports])),
        mean_top_quintile_return=float(
            np.mean([f.top_quintile_return for f in fold_reports])
        ),
    )
