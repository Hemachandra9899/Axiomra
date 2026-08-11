# Repository Research: Vibe-Trading

> Source: `/Users/teja/Documents/Vibe-Trading` — License: **MIT**

## Purpose

A broad "trading operating system" with LLM agents, skills, quant library,
broker interfaces, live safety and audit.

## Relevant directories

- `agent/src/live/` — `order_guard.py`, `enforcement.py`, `mandate/`,
  `halt.py`, `audit.py`, `daily_count.py`
- `agent/src/` — `channels/signal.py`, `shadow_account/`, `strategy_store/`,
  `governance/`, `quantlib/`

## Architecture worth borrowing

- **Mandate gate / order guard**: a deterministic pre-trade authority
  (`check_mandate`) that DENY/ALLOWs orders and refuses to trade without a
  valid, unexpired mandate. Mirrors Axiomra Guard's role as sole authority.
- **Halt flags / kill switch**: fail-closed circuit breaking.
- **Audit trail**: every live action recorded with
  `mandate_snapshot_ref` + `consent_record_ref` so orders trace back to
  authorizing clicks. Matches Axiomra's immutable decision journal.
- **Shadow accounts**: candidate strategies run without capital control.
- **SignalEngine pattern** in `channels/signal.py`: strategies implement a
  common signal-generation interface.

## Interfaces worth reproducing

- `SignalEngine.generate(features) -> signals` — see `axiomra/features` +
  `axiomra/quant/momentum.py` as the first implementation.
- Shadow/candidate strategy separation — Axiomra Lab later.

## What NOT to copy

- The full agent/tool/skill surface; V1 does not need it.
- Any mandate schema fields tied to Vibe's consent chain; Axiomra keeps its
  own risk policy versioning.

## Classification

**A — ADAPT** (concepts), **B — REIMPLEMENT** (code)

## Integration path

Axiomra Guard (`axiomra/risk/`) adopts the mandate/deny-by-default posture;
paper execution models the shadow-account idea.
