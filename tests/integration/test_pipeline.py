"""End-to-end pipeline tests.

The pipeline is the only place orders are created. These tests verify the
dependency chain Decision -> Portfolio -> Guard -> Execution -> Journal and
that no path bypasses risk approval.
"""

from __future__ import annotations

from datetime import UTC, datetime

from axiomra.agents.orchestrator import ResearchOrchestrator
from axiomra.data.repository import DataRepository
from axiomra.decision import DecisionConfig, DecisionEngine
from axiomra.domain.market import OHLCV, MarketSnapshot
from axiomra.execution.paper import PaperExecutionEngine
from axiomra.fusion.engine import SignalFusionEngine
from axiomra.pipeline import AxiomraPipeline, PipelineContext
from axiomra.portfolio.optimizer import PortfolioConfig, PortfolioOptimizer
from axiomra.quant.momentum import MomentumBaseline
from axiomra.risk.engine import RiskEngine, RiskPolicy


class RecordingRepository(DataRepository):
    """In-memory repo that records every save call."""

    def __init__(self) -> None:
        self.saves: list[dict] = []

    async def insert_bars(self, bars):  # pragma: no cover
        return len(bars)

    async def bars(self, symbol, start=None, end=None):  # pragma: no cover
        return []

    async def save_decision(self, candidate, signals, proposal, risk, execution):
        self.saves.append(
            {
                "candidate": candidate,
                "signals": signals,
                "proposal": proposal,
                "risk": risk,
                "execution": execution,
            }
        )
        return f"decision-{len(self.saves)}"


def MomentumFeatureDefaults() -> dict:
    return {
        "momentum_5d": 0.04,
        "momentum_20d": 0.12,
        "momentum_60d": 0.25,
        "volatility_20d": 0.02,
        "volume_ratio": 1.4,
        "distance_ema20": 0.03,
        "ret_1d": 0.008,
    }


def _snapshot(
    symbol="RELIANCE.NS",
    features: dict | None = None,
    regime: str = "TREND_UP",
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        bar=OHLCV(open=2480, high=2510, low=2460, close=2500, volume=4_000_000),
        features=features
        or {
            "momentum_5d": 0.04,
            "momentum_20d": 0.12,
            "momentum_60d": 0.25,
            "volatility_20d": 0.02,
            "volume_ratio": 1.4,
            "distance_ema20": 0.03,
            "ret_1d": 0.008,
        },
        market_regime=regime,
        data_version="test-v1",
    )


def _pipeline(repo: RecordingRepository) -> AxiomraPipeline:
    return AxiomraPipeline(
        decision_engine=DecisionEngine(
            quant_model=MomentumBaseline(),
            orchestrator=ResearchOrchestrator(agents=[]),
            fusion_engine=SignalFusionEngine(),
            config=DecisionConfig(no_trade_threshold=0.30),
        ),
        portfolio_engine=PortfolioOptimizer(config=PortfolioConfig()),
        risk_engine=RiskEngine(policy=RiskPolicy.defaults()),
        execution_engine=PaperExecutionEngine(),
        repository=repo,
    )


async def test_full_pipeline_executes_and_journals():
    repo = RecordingRepository()
    pipeline = _pipeline(repo)
    outcome = await pipeline.run(
        _snapshot(),
        PipelineContext(entry_price=2500, atr=30, portfolio_value=1_000_000),
    )

    assert outcome.status == "EXECUTED"
    assert outcome.decision is not None
    assert outcome.decision.action in {"LONG", "NO_TRADE"}
    if outcome.execution is not None:
        assert outcome.execution.is_filled

    # A decision must always be journaled, even if it did not trade.
    assert len(repo.saves) == 1
    assert repo.saves[0]["signals"]


async def test_no_trade_still_journaled():
    repo = RecordingRepository()
    pipeline = _pipeline(repo)
    # Weak features keep momentum near zero -> NO_TRADE.
    snapshot = _snapshot(features={**MomentumFeatureDefaults(), "momentum_20d": 0.001})
    outcome = await pipeline.run(
        snapshot,
        PipelineContext(entry_price=2500, atr=30, portfolio_value=1_000_000),
    )
    assert outcome.status == "NO_TRADE"
    assert outcome.execution is None
    assert len(repo.saves) == 1


async def test_risk_rejected_path_never_reaches_execution():
    repo = RecordingRepository()
    pipeline = _pipeline(repo)
    pipeline.portfolio.state.sector_exposure = {"UNKNOWN": 0.14}

    snapshot = _snapshot(features={**MomentumFeatureDefaults(), "momentum_20d": 0.15})
    outcome = await pipeline.run(
        snapshot,
        PipelineContext(entry_price=2500, atr=30, portfolio_value=1_000_000),
    )

    assert outcome.status == "RISK_REJECTED"
    assert outcome.execution is None
    assert "SECTOR_LIMIT" in outcome.reasons
    assert len(repo.saves) == 1


async def test_stale_data_blocks_order():
    repo = RecordingRepository()
    pipeline = _pipeline(repo)
    outcome = await pipeline.run(
        _snapshot(),
        PipelineContext(
            entry_price=2500,
            atr=30,
            portfolio_value=1_000_000,
            data_fresh=False,
        ),
    )
    assert outcome.status == "RISK_REJECTED"
    assert outcome.execution is None
    assert "STALE_DATA" in outcome.reasons
