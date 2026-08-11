"""Explicit version constants.

Every artifact a decision depends on must be versioned so that:

    decision -> which model? which prompt? which data? which risk policy?

These constants are the single source of truth for V1 versions. Bump them
when the corresponding artifact changes.
"""

from __future__ import annotations

# Model versions
MODEL_VERSION_MOMENTUM = "momentum-v1"
MODEL_VERSION_LIGHTGBM = "lgbm-v1"
MODEL_VERSION_ENSEMBLE = "ensemble-v1"

# Fusion
FUSION_VERSION = "fusion-v1"

# Risk policy
RISK_POLICY_VERSION = "risk-v1"

# Data / features
FEATURE_VERSION = "f-v1"
DATA_VERSION_PREFIX = "d"

# Decision engine
DECISION_ENGINE_VERSION = "decision-v1"
NO_TRADE_THRESHOLD = 0.30
