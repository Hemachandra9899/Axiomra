# Repository Research: OpenBB

> Source: `/Users/teja/Documents/OpenBB` — License: **AGPL-3.0**

## Purpose

Open-source investment research platform with a provider abstraction layer
over many market/fundamental/news data vendors.

## Relevant directories

- `openbb_platform/` — provider model, extension system, `core`

## Architecture worth borrowing

- **Provider abstraction**: a common data contract over interchangeable
  vendors (bars, fundamentals, news, etc.). Axiomra's data layer mirrors this
  with `MarketDataProvider` / `FundamentalDataProvider` / `NewsDataProvider`
  (see `axiomra/data/providers/base.py`).

## Interfaces worth reproducing

- `MarketDataProvider.bars(...)`, `FundamentalDataProvider.fundamentals(...)`,
  `NewsDataProvider.news(...)`.

## What NOT to copy

- AGPL-3.0 code must NOT be linked into Axiomra's proprietary core. Axiomra
  defines its own internal contracts; an OpenBB adapter (if ever needed)
  lives at the edge and may be optional/out-of-tree.
- Do not make OpenBB a hard dependency of the core.

## Classification

**C — INSPIRATION**

## Integration path

Axiomra Data adapter layer implements the internal provider ABCs. Vendor
adapter (yfinance first, then others) conforms to these contracts.
