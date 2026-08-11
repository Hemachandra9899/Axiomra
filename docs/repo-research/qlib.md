# Repository Research: qlib

> Source: `/Users/teja/Documents/qlib` — License: **MIT**

## Purpose

Microsoft Qlib is an AI-oriented quant investment platform separating
forecast models from portfolio strategies.

## Relevant directories

- `qlib/model` — ML models (LightGBM, XGBoost, transformer, ensembles)
- `qlib/data` — dataset/dataloader (point-in-time aware)
- `qlib/workflow` — train/predict pipeline
- `qlib/strategy` — signal/weight strategies
- `qlib/backtest` — `Backtest`, `PortAnaRecord`
- `qlib/contrib` — `model/highfreq`, `evaluate`

## Architecture worth borrowing

```text
FEATURES -> MODEL -> SCORE -> RANKING -> PORTFOLIO STRATEGY -> TARGET HOLDINGS
```

- `TopkDropoutStrategy` / `BaseSignalStrategy`: model scores are converted to
  target holdings by a *strategy*, never by the model itself. This is the
  core separation Axiomra reproduces: ML emits `score`, portfolio code decides
  quantity.
- Point-in-time dataset design: features are pre-computed with no lookahead.
- Model registry / `Record` mechanism for reproducible experiment metadata.

## Interfaces worth reproducing

- `QuantModel.predict(snapshot) -> QuantPrediction` (see `axiomra/quant/base.py`).
- Score->ranking->target-weight separation (see `axiomra/portfolio/optimizer.py`).

## Testing patterns

- Synthetic data fixtures used to validate model/dataset glue.
- Walk-forward split conventions for train/valid/test.

## What NOT to copy

- Deep coupling of data handlers to qlib's internal `ExpressionD` DSL for
  Axiomra's core; keep qlib behind the adapter.
- Qlib's backtest engine as Axiomra's execution layer (use LEAN for that).

## Classification

**B — REIMPLEMENT / adapter integration**

## Integration path

`axiomra/quant/qlib_adapter.py` implements `QuantModel` and serves qlib
trained models' scores into Axiomra's fusion pipeline.
