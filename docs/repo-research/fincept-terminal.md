# Repository Research: FinceptTerminal

> Source: `/Users/teja/Documents/FinceptTerminal` — License: **AGPL-3.0**

## Purpose

A desktop quant terminal for Indian markets with broker connectivity
(Zerodha, Dhan, Upstox) and a bundled LEAN fork.

## Relevant directories

- `fincept-qt/scripts/exchange/` — `place_order.py`, `cancel_order.py`,
  `exchange_daemon.py`, `broker_ws_bridge.py`, `fetch_markets.py`
- `fincept-qt/scripts/strategies/fincept_engine/` — bundled LEAN engine

## Architecture worth borrowing

- **Unified broker abstraction**: one exchange daemon dispatch pattern
  (`place_order`, `cancel_order`, markets cache) over multiple brokers with a
  WebSocket bridge for streaming. Axiomra reproduces this as a `Broker` ABC
  with adapters, but keeps margin/risk heuristics out — those must come from
  authoritative broker/exchange data.

## Interfaces worth reproducing

- `Broker.place_order / cancel_order / positions / balances`
  (see `axiomra/execution/base.py`).

## What NOT to copy

- AGPL-3.0 code must NOT be incorporated into Axiomra's proprietary core.
  Reference concepts only; reimplement all interfaces cleanly.
- Bundled LEAN fork internals — use upstream LEAN instead.
- Margin heuristics.

## Classification

**C — INSPIRATION** (licensing restricts reuse)

## Integration path

Axiomra's `BrokerExecutionEngine` design mirrors the unified adapter idea;
paper execution comes first, then Dhan/Zerodha/Upstox adapters behind the
same `ExecutionEngine` contract.
