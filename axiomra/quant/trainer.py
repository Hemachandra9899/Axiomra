"""Cross-sectional LightGBM trainer.

Trains a ranker/regressor on a checksummed `DatasetSnapshot`: features come
from the point-in-time safe feature pipeline, targets are forward returns at
a fixed horizon. The output is an Axiomra `LightGBMQuantModel` plus a
`TrainingReport` so training is auditable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

from axiomra.data.snapshot import DatasetSnapshot
from axiomra.features.pipeline import FeaturePipeline
from axiomra.quant.lightgbm import DEFAULT_FEATURES, LightGBMQuantModel

try:  # pragma: no cover - exercised only when lightgbm is present
    import lightgbm as lgbm
except ImportError:  # pragma: no cover
    lgbm = None  # type: ignore[assignment]

DEFAULT_HORIZON_DAYS = 5


def forward_return(close: pd.Series, horizon: int = DEFAULT_HORIZON_DAYS) -> pd.Series:
    """Return over the next `horizon` bars: close[t+h] / close[t] - 1.

    Rows without a future close (the last `horizon` rows) become NaN and are
    dropped by `build_training_frame`, so no label leakage is possible.
    """
    return close.shift(-horizon) / close - 1.0


def build_training_frame(
    snapshot: DatasetSnapshot,
    horizon: int = DEFAULT_HORIZON_DAYS,
    feature_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Stack per-symbol feature rows into one long frame with a target.

    Columns: symbol, date, <features>, target. The frame is sorted by date so
    cross-sectional row order is deterministic.
    """
    pipeline = FeaturePipeline()
    columns = feature_columns or pipeline.output_columns
    frames: list[pd.DataFrame] = []

    for symbol, bars in snapshot.bars.items():
        df = pd.DataFrame(
            {
                "date": [b.timestamp for b in bars],
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            }
        ).set_index("date")

        featured = pipeline.compute(df)
        featured["target"] = forward_return(featured["close"], horizon)
        featured["symbol"] = symbol
        featured = featured.reset_index()

        # Keep only requested features that carry any signal; a column that is
        # all-NaN (e.g. a 200-day EMA on 60 days of data) is dropped.
        usable = [
            c for c in columns if c in featured.columns and featured[c].notna().any()
        ]
        featured = featured[["symbol", "date", "target", *usable]]
        frames.append(featured)

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames, ignore_index=True)
    feature_cols = [c for c in full.columns if c not in {"symbol", "date", "target"}]
    full = full.dropna(subset=["target", *feature_cols])
    return full.sort_values(["date", "symbol"]).reset_index(drop=True)


def _default_lgbm_params() -> dict:
    return {
        "objective": "regression",
        "metric": "l2",
        "n_estimators": 300,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 20,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "verbosity": -1,
        "random_state": 42,
    }


class TrainingReport(BaseModel):
    """Auditable record of a training run."""

    model_name: str
    model_version: str
    horizon: int
    feature_columns: list[str]
    rows: int
    dropped_rows: int
    feature_importances: dict[str, float]
    train_ic: float
    n_estimators: int


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation, robust to NaN-free inputs."""
    if len(a) < 2:
        return 0.0
    a_rank = pd.Series(a).rank().values
    b_rank = pd.Series(b).rank().values
    a_c = a_rank - a_rank.mean()
    b_c = b_rank - b_rank.mean()
    denom = np.sqrt((a_c**2).sum() * (b_c**2).sum())
    if denom == 0:
        return 0.0
    return float(np.dot(a_c, b_c) / denom)


def train_lightgbm_model(
    snapshot: DatasetSnapshot,
    horizon: int = DEFAULT_HORIZON_DAYS,
    feature_columns: list[str] | None = None,
    params: dict | None = None,
    model_version: str = "lgbm-v2",
) -> tuple[LightGBMQuantModel, TrainingReport]:
    """Train a cross-sectional LightGBM model on a dataset snapshot.

    Returns (model, report). The model is a ready-to-use Axiomra quant model;
    the report binds features, data and fit quality for the journal.
    """
    if lgbm is None:
        raise ImportError(
            "train_lightgbm_model requires the 'lightgbm' package. "
            "Install Axiomra with: pip install 'axiomra[ml]'"
        )

    columns = feature_columns or DEFAULT_FEATURES
    frame = build_training_frame(snapshot, horizon=horizon)
    if frame.empty:
        raise ValueError("training frame is empty: no usable bars after dropping NaN rows")

    feature_cols = [c for c in columns if c in frame.columns]
    if not feature_cols:
        raise ValueError(f"no requested features present in frame: {columns}")

    x = frame[feature_cols].to_numpy(dtype=float)
    y = frame["target"].to_numpy(dtype=float)
    total_rows = frame.shape[0] + int(
        sum(horizon for bars in snapshot.bars.values() if bars)
    )
    dropped_rows = max(0, total_rows - frame.shape[0])

    merged = {**_default_lgbm_params(), **(params or {})}
    n_estimators = int(merged.pop("n_estimators", 300))

    model = lgbm.LGBMRegressor(**merged, n_estimators=n_estimators)
    model.fit(x, y)

    preds = model.predict(x)
    train_ic = _spearman(preds, y)

    importances = dict(
        zip(feature_cols, (model.feature_importances_ / max(1, model.feature_importances_.sum())).tolist())
    )

    report = TrainingReport(
        model_name="lightgbm",
        model_version=model_version,
        horizon=horizon,
        feature_columns=feature_cols,
        rows=int(frame.shape[0]),
        dropped_rows=dropped_rows,
        feature_importances=importances,
        train_ic=train_ic,
        n_estimators=n_estimators,
    )

    return LightGBMQuantModel(
        model=model,
        features=feature_cols,
        confidence=0.75,
        model_version=model_version,
    ), report
