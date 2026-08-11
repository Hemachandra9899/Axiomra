# Repository Research: tradingagents

> Source: `/Users/teja/Documents/tradingagents` — License: **Apache 2.0**

## Purpose

Multi-agent LLM framework for trading research and decision-making.

## Relevant directories

- `tradingagents/graph/` — `trading_graph.py`, `setup.py`,
  `conditional_logic.py`, `signal_processing.py`, `propagation.py`
- `tradingagents/agents/` — agent definitions + `schemas.py` (structured I/O)
- `tradingagents/llm_clients` — provider abstractions

## Architecture worth borrowing

- Multi-role research pipeline: Market/Technical, Fundamental, News/Sentiment,
  Bull vs Bear researchers, Trader, Risk debate, Portfolio manager.
- **Structured agent output**: `TraderProposal` and schema-validated returns
  instead of free-form prose (matches Axiomra's `StructuredOutput`).
- Independent analysts run before any trade decision.

## Interfaces worth reproducing

- `ResearchAgent.analyze(snapshot) -> EvidenceSignal`
  (see `axiomra/agents/base.py`).
- Skeptic / risk-debate pattern: opposing views lower confidence rather than
  vote directly.

## What NOT to copy

- Agents that produce orders directly. Axiomra agents return evidence only.
- The entire multi-agent graph; V1 uses exactly four agents
  (Technical, Fundamental, News, Skeptic).

## Classification

**A — ADAPT** (concepts), **B — REIMPLEMENT** (code)

## Integration path

`axiomra/agents/orchestrator.py` runs the four V1 research agents over a
candidate funnel produced by the quant engine.
