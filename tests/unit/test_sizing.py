"""Position sizing and caps."""

from __future__ import annotations

from axiomra.portfolio.sizing import (
    PositionSizeRequest,
    apply_position_cap,
    calculate_quantity,
)


def test_risk_budget_formula():
    # Portfolio 10L, 0.5% risk, ATR 35, 2 ATR stop => qty 71
    qty = calculate_quantity(
        PositionSizeRequest(
            portfolio_value=1_000_000,
            entry_price=2500.0,
            atr=35.0,
        )
    )
    assert qty == 71


def test_zero_atr_gives_zero():
    assert (
        calculate_quantity(
            PositionSizeRequest(portfolio_value=1_000_000, entry_price=100, atr=0.0)
        )
        == 0
    )


def test_position_cap_wins_when_smaller():
    qty = apply_position_cap(
        quantity=1000,
        price=1000.0,
        portfolio_value=1_000_000,
        max_position_pct=0.03,
    )
    # max value 30,000 / 1000 = 30
    assert qty == 30


def test_risk_budget_wins_when_smaller():
    qty = apply_position_cap(
        quantity=20,
        price=1000.0,
        portfolio_value=1_000_000,
        max_position_pct=0.03,
    )
    assert qty == 20


def test_cap_nonpositive_price():
    assert apply_position_cap(100, 0.0, 1_000_000) == 0
