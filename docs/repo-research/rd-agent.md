# Repository Research: RD-Agent

> Source: `/Users/teja/Documents` (RD-Agent referenced by design)
> License: MIT

## Purpose

Microsoft RD-Agent automates the R&D loop: hypothesis generation, coding,
running experiments, evaluation, feedback.

## Relevant directories

- `components/workflow/rd_loop.py` — the research loop
- `app/qlib_rd_loop/` — financial factor research workflow on Qlib

## Architecture worth borrowing

- **Research lifecycle**: Hypothesis -> Experiment -> Coding -> Running ->
  Evaluation -> Feedback -> Next hypothesis.
- Financial workflow: develop factors, validate quantitatively, backtest with
  Qlib — exactly Axiomra Lab's scope.

## Interfaces worth reproducing

- `Experiment` object (see `axiomra/research/`):
  hypothesis, baseline vs candidate, train/validation/test periods, metrics,
  status PROPOSED -> RUNNING -> VALIDATED -> PAPER -> SHADOW -> APPROVED ->
  PRODUCTION.

## What NOT to copy

- Never allow RD-Agent to modify production models, risk rules, or deploy
  strategies automatically. Generated code goes to `research/generated/`.

## Classification

**C — INSPIRATION** (integrate as an external offline service)

## Integration path

Axiomra Lab wraps RD-Agent as an offline researcher once the data/model/
backtest/evaluation pipeline exists.
