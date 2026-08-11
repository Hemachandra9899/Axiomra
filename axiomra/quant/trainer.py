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

from axiomra.data.instruments import InstrumentMaster
from axiomra.data.snapshot import DatasetSnapshot
from axiomra.features.pipeline import FeaturePipeline
from axiomra.quant.lightgbm import DEFAULT_FEATURES, LightGBMQuantModel

try:  # pragma: no cover - exercised only when lightgbm is present

    import lightgbm as lgbm
except ImportError:  # pragma: no cover
    lgbm = None  # type: ignore[assignment]

DEFAULT_HORIZON_DAYS = 5


def execution_aligned_return(
    close: pd.Series,
    open_: pd.Series,
    horizon: int = DEFAULT_HORIZON_DAYS,
) -> pd.Series:
    """Execution-aligned return over `horizon` bars: close[t+h] / open[t+1] - 1.

    Entry occurs at open of T+1 and exit occurs at close of T+h.
    """
    return close.shift(-horizon) / open_.shift(-1) - 1.0


def close_to_close_forward_return(
    close: pd.Series,
    horizon: int = DEFAULT_HORIZON_DAYS,
) -> pd.Series:
    """Close-to-close fallback return over `horizon` bars: close[t+h] / close[t] - 1."""
    return close.shift(-horizon) / close - 1.0


def forward_return(
    close: pd.Series,
    open_: pd.Series | None = None,
    horizon: int = DEFAULT_HORIZON_DAYS,
) -> pd.Series:
    """Return over `horizon` bars.

    Delegates to `execution_aligned_return` when `open_` is provided, or
    `close_to_close_forward_return` when `open_` is None.
    """
    if open_ is not None:
        return execution_aligned_return(close, open_, horizon)
    return close_to_close_forward_return(close, horizon)


def build_training_frame(

    snapshot: DatasetSnapshot,
    horizon: int = DEFAULT_HORIZON_DAYS,
    feature_columns: list[str] | None = None,
    instruments: InstrumentMaster | None = None,
) -> pd.DataFrame:
    """Stack per-symbol feature rows into one long frame with a target and label metadata.

    Columns: symbol, date, label_start, label_end, <features>, target. The frame is sorted by date so
    cross-sectional row order is deterministic. Point-in-time index membership is enforced via instrument_id/symbol
    when snapshot.memberships is provided (preventing survivorship bias).
    """
    pipeline = FeaturePipeline()
    columns = feature_columns or pipeline.output_columns
    frames: list[pd.DataFrame] = []

    membership_registry: HistoricalUniverseRegistry | None = None
    if snapshot.memberships:
        from axiomra.data.universe import HistoricalUniverseRegistry

        membership_registry = HistoricalUniverseRegistry()
        for m in snapshot.memberships:
            membership_registry.add_membership(m)

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
        featured["target"] = execution_aligned_return(featured["close"], featured["open"], horizon)
        featured["symbol"] = symbol
        featured = featured.reset_index()

        # Point-in-Time Survivorship Bias Filter: Drop rows where instrument_id or symbol was NOT an active index member
        if membership_registry is not None:
            is_member_mask = []
            for row_date in featured["date"]:
                target_id = symbol
                if instruments is not None:
                    inst = instruments.resolve_symbol(symbol, row_date)
                    if inst is not None:
                        target_id = inst.instrument_id

                is_member_mask.append(
                    membership_registry.is_member(target_id, row_date)
                    or membership_registry.is_member(symbol, row_date)
                )
            featured = featured[is_member_mask]

        if featured.empty:
            continue


        dates = featured["date"]
        featured["label_start"] = dates.shift(-1)
        featured["label_end"] = dates.shift(-horizon)

        # Keep only requested features that carry any signal; a column that is
        # all-NaN (e.g. a 200-day EMA on 60 days of data) is dropped.
        usable = [
            c for c in columns if c in featured.columns and featured[c].notna().any()
        ]
        featured = featured[["symbol", "date", "label_start", "label_end", "target", *usable]]
        frames.append(featured)

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames, ignore_index=True)
    feature_cols = [
        c for c in full.columns if c not in {"symbol", "date", "label_start", "label_end", "target"}
    ]
    full = full.dropna(subset=["target", "label_start", "label_end", *feature_cols])
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
