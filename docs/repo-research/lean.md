# Repository Research: Lean

> Source: `/Users/teja/Documents/lean` — License: **Apache 2.0**

## Purpose

QuantConnect LEAN, an event-driven algorithmic trading engine (Python/C#).

## Relevant directories

- `Algorithm.Framework/` — Universe Selection, Alpha, Portfolio Construction,
  Risk Management, Execution models
- `Algorithm/` — `QCAlgorithm`
- `Brokerages/` — brokerage adapters
- `Engine/` — event-driven data/order loops

## Architecture worth borrowing

- **Algorithm Framework layering**: Universe -> Alpha -> Portfolio
  Construction -> Risk Management -> Execution. Maps directly to Axiomra:

```text
Universe        -> NIFTY 200 + quant filter
Alpha           -> Quant + AI research
Portfolio       -> Axiomra Portfolio
Risk Management -> Axiomra Guard
Execution       -> Axiomra Execution
```

- Event-driven order lifecycle: NEW -> SUBMITTED -> PARTIALLY_FILLED ->
  FILLED / REJECTED / CANCELLED (reproduced in `axiomra/domain/orders.py`).

## Interfaces worth reproducing

- `ExecutionEngine.submit(order)` (see `axiomra/execution/base.py`).
- A `LeanExecutionEngine` adapter later, keeping LEAN as a service boundary —
  never embedded in business logic.

## What NOT to copy

- Tight coupling of strategy logic to `QCAlgorithm`. Axiomra owns the decision
  pipeline; LEAN only executes/backtests.

## Classification

**B — REIMPLEMENT** (interfaces), **D — REJECT** (deep coupling)

## Integration path

`LeanExecutionEngine` adapter for backtesting and paper execution; Axiomra's
`DecisionEngine` remains independent.
