"""Execution planning from position deltas.

Orders are derived from the gap between the current position and the target
position — never from an action label alone:

    Current  Target   Delta   Order
    2%       4%       +2%     BUY
    4%       1%       -3%     SELL
    0%       0%        0%     none
    0%       -x        -x     none (long-only V1: no shorting)

This structurally prevents a REDUCE signal from ever producing a BUY.
"""

from __future__ import annotations

from axiomra.domain.orders import OrderRequest, OrderSide


def plan_order(
    *,
    symbol: str,
    action: str,
    current_quantity: int,
    target_quantity: int,
    decision_id: str | None = None,
    min_delta: int = 1,
) -> OrderRequest | None:
    """Turn (current, target) into an order, or None when nothing to do.

    Long-only V1: a negative delta on a zero position is a no-op (no shorting).
    """
    delta = target_quantity - current_quantity

    if abs(delta) < min_delta:
        return None

    if delta > 0:
        return OrderRequest(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=delta,
            decision_id=decision_id,
        )

    if current_quantity <= 0:
        return None

    return OrderRequest(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=-delta,
        decision_id=decision_id,
    )


def plan_reduce(
    symbol: str,
    current_quantity: int,
    decision_id: str | None = None,
) -> OrderRequest | None:
    """V1 long-only reduction: exit the whole position."""
    if current_quantity <= 0:
        return None
    return OrderRequest(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=current_quantity,
        decision_id=decision_id,
    )


def resolve_order_side(
    action: str,
    current_quantity: int,
) -> OrderSide | None:
    """Determine the order side for long-only V1 given an action and current position.

    A LONG signal returns BUY.
    A REDUCE signal on an existing position returns SELL.
    A REDUCE signal on zero holding returns None (no shorting in long-only V1).
    """
    if action == "LONG":
        return OrderSide.BUY
    if action == "REDUCE" and current_quantity > 0:
        return OrderSide.SELL
    return None

