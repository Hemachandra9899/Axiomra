# Repository Audit Summary

| Repository     | License   | Classification                        | Use in Axiomra                              |
| -------------- | --------- | ------------------------------------- | ------------------------------------------- |
| qlib           | MIT       | B — REIMPLEMENT / adapter             | Quant models, score->rank separation        |
| tradingagents  | Apache-2  | A — ADAPT concepts / B — code         | Multi-agent research, structured outputs    |
| Vibe-Trading   | MIT       | A — ADAPT concepts / B — code         | Mandate gate posture, audit, shadow account |
| FinceptTerminal| AGPL-3.0  | C — INSPIRATION (no reuse)            | Unified broker interface concept only       |
| OpenBB         | AGPL-3.0  | C — INSPIRATION (no reuse)            | Provider abstraction concept only           |
| lean           | Apache-2  | B — REIMPLEMENT interfaces / D—deep   | Backtest/paper execution service boundary   |
| nautilus_trader| LGPL-3.0  | C — INSPIRATION                       | Event/state modeling patterns               |
| RD-Agent       | MIT       | C — INSPIRATION (external service)    | Axiomra Lab offline researcher              |

Rules applied:

- No LLM or quant model reaches a broker.
- AGPL/LGPL code is never incorporated into Axiomra's proprietary core.
- Reference repos are read-only; nothing is copied wholesale.
