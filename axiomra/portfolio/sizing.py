"""Risk-based position sizing.

AI never sets quantity. The portfolio engine does, using the ATR-based
risk budget formula:

    risk_budget  = portfolio_value * risk_fraction
    stop_distance = atr * atr_multiplier
    quantity     = floor(risk_budget / stop_distance)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionSizeRequest:
    portfolio_value: float
    entry_price: float
    atr: float
    risk_fraction: float = 0.005
    atr_multiplier: float = 2.0


def calculate_quantity(req: PositionSizeRequest) -> int:
    """Quantity from risk budget and stop distance. Never negative."""
    risk_budget = req.portfolio_value * req.risk_fraction
    stop_distance = req.atr * req.atr_multiplier

    if stop_distance <= 0:
        return 0

    return max(int(risk_budget / stop_distance), 0)


def apply_position_cap(
    quantity: int,
    price: float,
    portfolio_value: float,
    max_position_pct: float = 0.03,
) -> int:
    """Cap a position at a fraction of portfolio value.

    The smaller of risk-based size and concentration cap wins.
    """
    if price <= 0 or portfolio_value <= 0:
        return 0

    max_value = portfolio_value * max_position_pct
    max_quantity = int(max_value / price)

    return min(quantity, max(0, max_quantity))
