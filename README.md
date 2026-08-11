# Axiomra

**Axiomra — Evidence-Driven AI Quant Intelligence**

Axiomra is a decision system, not an autonomous trading agent. It separates
research from prediction, prediction from evidence fusion, fusion from
portfolio construction, and everything from execution authority.

## Architecture

```text
DATA
  -> FEATURE ENGINE
  -> QUANT ENGINE  +  AI RESEARCH
  -> SIGNAL FUSION
  -> PORTFOLIO ENGINE
  -> AXIOMRA GUARD  (deterministic risk authority)
  -> EXECUTION ENGINE  (paper / LEAN / broker)
  -> JOURNAL
  -> ATTRIBUTION
  -> RESEARCH LAB
```

## Non-negotiable rules

- An LLM never calls a broker.
- A quant model never calls a broker.
- Only the pipeline `Quant + Agents -> Candidate -> Portfolio -> Guard -> Execution`
  may generate orders.
- Every prediction is reproducible: `data_version`, `model_version`,
  `prompt_version`, `risk_policy_version`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Milestones

1. NIFTY 200 data -> features -> momentum baseline + LightGBM -> ranked
   opportunities -> portfolio sizing -> Guard -> paper trades -> journal.
2. Qlib adapter + model registry + calibration.
3. AI research agents + fusion.
4. LEAN adapter + execution simulation.
5. Attribution + research lab (RD-Agent).
