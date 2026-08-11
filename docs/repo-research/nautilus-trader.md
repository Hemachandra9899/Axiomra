# Repository Research: nautilus_trader

> Source: `/Users/teja/Documents/nautilus_trader` — License: **LGPL-3.0**

## Purpose

High-performance event-driven algorithmic trading platform in Python.

## Relevant directories

- `nautilus_trader/model/events/` — market/order/position events
- `nautilus_trader/model/objects/` — orders, position, account state
- `nautilus_trader/portfolio/` — position management
- `nautilus_trader/execution/` — engines, algorithms
- `nautilus_trader/risk/` — risk engine with limits and pre-trade checks

## Architecture worth borrowing

- **Event-driven state machine**: MarketEvent -> Strategy -> Order proposal ->
  Risk -> Execution -> Order events -> Position updates. Axiomra reproduces
  this as its domain event sequence.
- **Risk engine with configurable limits** evaluated pre-trade.
- **Cache/order-factory** patterns for consistent object creation.

## Interfaces worth reproducing

- Event models: `MarketEvent`, `OrderEvent`, `FillEvent`, `PositionEvent`
  (Axiomra's `axiomra/domain/` captures the same state).

## What NOT to copy

- LGPL-3.0 code into the proprietary core — reference architecture only.
- Replacing Axiomra's own execution abstraction with Nautilus internals.

## Classification

**C — INSPIRATION**

## Integration path

Axiomra's event/state modeling follows Nautilus's separation of market state,
order state, and risk authority.
