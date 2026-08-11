"""Point-in-time safe feature computation.

All features are computed with rolling/lag operators only, so a feature
value at row `t` never uses information from rows `> t`. Corporate actions
and survivorship issues are handled upstream at ingestion time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_VERSION = "f-v1"


def _safe(pct: pd.Series) -> pd.Series:
    """Replace infinite/NaN percentages so downstream math stays valid."""
    return pct.replace([np.inf, -np.inf], np.nan)


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute core features from a OHLCV frame indexed by timestamp.

    Required input columns: open, high, low, close, volume.
    Returns the same frame augmented with feature columns.
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = df.copy()

    # --- Momentum ---
    out["ret_1d"] = _safe(out["close"].pct_change(1))
    out["momentum_5d"] = _safe(out["close"].pct_change(5))
    out["momentum_20d"] = _safe(out["close"].pct_change(20))
    out["momentum_60d"] = _safe(out["close"].pct_change(60))

    # --- Moving averages / trend ---
    out["ema_20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["ema_50"] = out["close"].ewm(span=50, adjust=False).mean()
    out["ema_200"] = out["close"].ewm(span=200, adjust=False).mean()

    out["distance_ema20"] = out["close"] / out["ema_20"] - 1.0
    out["trend_ema50"] = out["ema_20"] / out["ema_50"] - 1.0

    # --- Volatility ---
    out["volatility_20d"] = out["ret_1d"].rolling(20).std()
    out["volatility_60d"] = out["ret_1d"].rolling(60).std()

    # --- ATR (14) ---
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - out["close"].shift(1)).abs(),
            (out["low"] - out["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_14"] = tr.ewm(span=14, adjust=False).mean()

    # --- RSI (14) ---
    delta = out["close"].diff()
    gain = delta.clip(lower=0.0).ewm(span=14, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi_14"] = 100.0 - 100.0 / (1.0 + rs)

    # --- Volume ---
    out["volume_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["volume_ma20"]

    # --- Relative strength vs. a benchmark series (optional) ---
    if "benchmark" in out.columns:
        out["relative_strength"] = _safe(
            out["close"].pct_change(20) - out["benchmark"].pct_change(20)
        )

    out.attrs["feature_version"] = FEATURE_VERSION
    return out


class FeaturePipeline:
    """Stateful wrapper around the pure feature computation."""

    version = FEATURE_VERSION

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        return calculate_features(df)

    def latest_features(self, df: pd.DataFrame) -> dict[str, float]:
        """Feature dict of the most recent bar. NaNs become None upstream."""
        result = self.compute(df)
        if result.empty:
            return {}
        last = result.iloc[-1]
        return {name: float(last[name]) for name in self.output_columns if name in last}

    @property
    def output_columns(self) -> list[str]:
        return [
            "ret_1d",
            "momentum_5d",
            "momentum_20d",
            "momentum_60d",
            "ema_20",
            "ema_50",
            "distance_ema20",
            "trend_ema50",
            "volatility_20d",
            "volatility_60d",
            "atr_14",
            "rsi_14",
            "volume_ma20",
            "volume_ratio",
        ]
