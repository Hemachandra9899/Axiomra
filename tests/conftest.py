from __future__ import annotations

import numpy as np
import pandas as pd


def make_ohlcv(n: int = 260, seed: int = 7, price: float = 100.0) -> pd.DataFrame:
    """Synthetic OHLCV frame with a mild upward drift."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n)
    rets = rng.normal(0.0005, 0.015, n)
    close = price * np.cumprod(1 + rets)
    open_ = close * (1 + rng.normal(0, 0.003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, n)))
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
