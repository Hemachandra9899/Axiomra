"""Paper execution engine tests."""

from __future__ import annotations

import random

from axiomra.domain.orders import OrderRequest
from axiomra.execution.paper import PaperExecutionConfig, PaperExecutionEngine


def _order(symbol="ABC", quantity=100, side="BUY") -> OrderRequest:
    return OrderRequest(symbol=symbol, side=side, quantity=quantity)


def test_basic_fill():
    engine = PaperExecutionEngine(
        config=PaperExecutionConfig(reference_price=100.0)
    )
    result = asyncio_run(engine.submit(_order()))
    assert result.status == "FILLED"
    assert result.filled_quantity == 100
    assert result.avg_fill_price == 100.0
    assert result.order_id


def test_slippage_penalizes_buy_and_sell():
    engine = PaperExecutionEngine(
        config=PaperExecutionConfig(reference_price=100.0, slippage_bps=50)
    )
    buy = asyncio_run(engine.submit(_order(side="BUY")))
    sell = asyncio_run(engine.submit(_order(side="SELL")))
    assert buy.avg_fill_price < 100.0
    assert sell.avg_fill_price > 100.0


def test_rejection():
    engine = PaperExecutionEngine(
        config=PaperExecutionConfig(reject_probability=1.0),
        rng=random.Random(1),
    )
    result = asyncio_run(engine.submit(_order()))
    assert result.status == "REJECTED"
    assert result.filled_quantity == 0


def test_partial_fill():
    engine = PaperExecutionEngine(
        config=PaperExecutionConfig(
            partial_fill_probability=1.0,
            partial_fill_ratio=0.5,
        ),
        rng=random.Random(1),
    )
    result = asyncio_run(engine.submit(_order(quantity=100)))
    assert result.status == "PARTIALLY_FILLED"
    assert result.filled_quantity == 50


def test_cancel_known_order():
    engine = PaperExecutionEngine()
    result = asyncio_run(engine.submit(_order()))
    assert asyncio_run(engine.cancel(result.order_id)) is True
    assert asyncio_run(engine.cancel("missing")) is False


def test_market_order_requires_no_limit_price():
    result = asyncio_run(PaperExecutionEngine().submit(_order()))
    assert result.is_filled


def asyncio_run(coro):
    import asyncio

    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
