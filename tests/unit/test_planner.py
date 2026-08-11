"""Target-position delta planning.

Orders must derive from the current->target gap, never from an action label.
A REDUCE on a zero position is a no-op; a LONG already at target is a no-op.
"""

from __future__ import annotations

from axiomra.domain.orders import OrderSide
from axiomra.portfolio.planner import plan_order, plan_reduce


def test_long_with_positive_delta_buys():
    order = plan_order(
        symbol="ABC",
        action="LONG",
        current_quantity=0,
        target_quantity=75,
    )
    assert order is not None
    assert order.side == OrderSide.BUY
    assert order.quantity == 75


def test_long_target_already_reached_no_order():
    order = plan_order(
        symbol="ABC",
        action="LONG",
        current_quantity=75,
        target_quantity=75,
    )
    assert order is None


def test_downsize_sells_excess_to_target():
    """A LONG whose target is below current downsizes the position."""
    order = plan_order(
        symbol="ABC",
        action="LONG",
        current_quantity=100,
        target_quantity=75,
    )
    assert order is not None
    assert order.side == OrderSide.SELL
    assert order.quantity == 25


def test_reduce_with_existing_holding_sells():
    order = plan_order(
        symbol="ABC",
        action="REDUCE",
        current_quantity=100,
        target_quantity=0,
    )
    assert order is not None
    assert order.side == OrderSide.SELL
    assert order.quantity == 100


def test_reduce_with_zero_holding_no_order():
    order = plan_order(
        symbol="ABC",
        action="REDUCE",
        current_quantity=0,
        target_quantity=0,
    )
    assert order is None


def test_reduce_cannot_buy_ever():
    """The original bug: bearish REDUCE must never produce a BUY."""
    for current in (0, 5, 100):
        order = plan_order(
            symbol="ABC",
            action="REDUCE",
            current_quantity=current,
            target_quantity=0,
        )
        assert order is None or order.side == OrderSide.SELL


def test_partial_reduce_sells_difference():
    order = plan_order(
        symbol="ABC",
        action="REDUCE",
        current_quantity=100,
        target_quantity=40,
    )
    assert order is not None
    assert order.side == OrderSide.SELL
    assert order.quantity == 60


def test_min_delta_ignores_rounding_noise():
    order = plan_order(
        symbol="ABC",
        action="LONG",
        current_quantity=74,
        target_quantity=75,
        min_delta=2,
    )
    assert order is None


def test_plan_reduce_exits_position():
    order = plan_reduce("ABC", current_quantity=50)
    assert order is not None
    assert order.side == OrderSide.SELL
    assert order.quantity == 50
    assert plan_reduce("ABC", current_quantity=0) is None
