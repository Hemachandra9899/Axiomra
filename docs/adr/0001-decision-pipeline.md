# ADR-0001 — Axiomra is a decision pipeline, not an autonomous agent

## Status

Accepted.

## Context

LLM agents that "place trades" produce arbitrary quantities with no
accountability. Axiomra needs repeatable, auditable decisions.

## Decision

Orders may only be produced by the pipeline:

```text
Quant + Agents -> Candidate -> Portfolio -> Axiomra Guard -> Execution
```

- Agents and quant models return structured signals only.
- Portfolio engine sizes positions deterministically (ATR risk budget +
  position cap).
- Guard is the sole approval authority; `approved=False` blocks orders.
- Everything is journaled with data/model/prompt/risk-policy versions.

## Consequences

- Reproducible decisions and explainable rejections (e.g. "blocked by
  SECTOR_LIMIT").
- More code than a single-agent demo, but a real product surface.
