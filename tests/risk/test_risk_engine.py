"""Axiomra Guard tests — the authority boundary."""

from __future__ import annotations

from datetime import UTC

import pytest

from axiomra.risk.context import RiskContext
from axiomra.risk.engine import RiskDecision, RiskEngine, RiskPolicy
from axiomra.risk.rules import (
    CorrelationLimitRule,
    DailyLossLimitRule,
    DataFreshnessRule,
    DrawdownLimitRule,
    EventRiskRule,
    LiquidityRule,
    PositionCountRule,
    PositionLimitRule,
    SectorLimitRule,
)


def _ctx(**overrides) -> RiskContext:
    base = dict(
        portfolio_value=1_000_000,
        daily_pnl_pct=0.0,
        drawdown_pct=0.0,
        projected_position_pct=0.02,
        projected_sector_pct=0.05,
        position_count=5,
    )
    base.update(overrides)
    return RiskContext(**base)


@pytest.mark.parametrize(
    "rule,ctx,expect_pass",
    [
        (DataFreshnessRule(), _ctx(data_fresh=True), True),
        (DataFreshnessRule(), _ctx(data_fresh=False), False),
        (LiquidityRule(), _ctx(liquidity_ok=True), True),
        (LiquidityRule(), _ctx(liquidity_ok=False), False),
        (EventRiskRule(), _ctx(event_risk=False), True),
        (EventRiskRule(), _ctx(event_risk=True), False),
        (PositionLimitRule(max_position_pct=0.03), _ctx(projected_position_pct=0.03), True),
        (PositionLimitRule(max_position_pct=0.03), _ctx(projected_position_pct=0.031), False),
        (SectorLimitRule(max_sector_pct=0.15), _ctx(projected_sector_pct=0.15), True),
        (SectorLimitRule(max_sector_pct=0.15), _ctx(projected_sector_pct=0.16), False),
        (CorrelationLimitRule(), _ctx(projected_correlation_pct=0.19), True),
        (CorrelationLimitRule(), _ctx(projected_correlation_pct=0.21), False),
        (DailyLossLimitRule(), _ctx(daily_pnl_pct=-0.005), True),
        (DailyLossLimitRule(), _ctx(daily_pnl_pct=-0.02), False),
        (DrawdownLimitRule(), _ctx(drawdown_pct=-0.05), True),
        (DrawdownLimitRule(), _ctx(drawdown_pct=-0.12), False),
        (PositionCountRule(max_positions=20), _ctx(position_count=19), True),
        (PositionCountRule(max_positions=20), _ctx(position_count=20), False),
    ],
)
def test_individual_rules(rule, ctx, expect_pass):
    check = rule.check(ctx)
    assert check.passed is expect_pass, check.reason


def test_boundary_daily_loss_is_a_violation():
    # Exactly at the limit counts as a violation (<= semantics per spec).
    rule = DailyLossLimitRule(max_daily_loss_pct=-0.01)
    assert rule.check(_ctx(daily_pnl_pct=-0.01)).passed is False
    assert rule.check(_ctx(daily_pnl_pct=-0.009)).passed is True


def test_full_engine_approves_clean_context():
    engine = RiskEngine(policy=RiskPolicy.defaults())
    decision = engine.evaluate(_ctx())
    assert isinstance(decision, RiskDecision)
    assert decision.approved is True
    assert decision.reasons == []


def test_stale_data_rejects():
    engine = RiskEngine()
    decision = engine.evaluate(_ctx(data_fresh=False))
    assert decision.approved is False
    assert "STALE_DATA" in decision.reasons


def test_position_limit_rejects():
    engine = RiskEngine()
    decision = engine.evaluate(_ctx(projected_position_pct=0.05))
    assert decision.approved is False
    assert "POSITION_LIMIT" in decision.reasons


def test_sector_limit_rejects():
    engine = RiskEngine()
    decision = engine.evaluate(_ctx(projected_sector_pct=0.30))
    assert decision.approved is False
    assert "SECTOR_LIMIT" in decision.reasons


def test_multiple_violations_all_reported():
    engine = RiskEngine()
    decision = engine.evaluate(
        _ctx(
            data_fresh=False,
            projected_position_pct=0.10,
            projected_sector_pct=0.40,
            daily_pnl_pct=-0.05,
            drawdown_pct=-0.20,
            event_risk=True,
        )
    )
    assert decision.approved is False
    for reason in ("STALE_DATA", "POSITION_LIMIT", "SECTOR_LIMIT", "DAILY_LOSS_LIMIT", "PORTFOLIO_DRAWDOWN", "EVENT_RISK"):
        assert reason in decision.reasons


def test_policy_version_is_recorded():
    policy = RiskPolicy.defaults(version="risk-v1")
    engine = RiskEngine(policy=policy)
    decision = engine.evaluate(_ctx())
    assert "risk-v1" in decision.policy_version


def test_no_order_can_be_created_when_risk_fails():
    """The pipeline must short-circuit before ExecutionEngine sees an order."""
    from axiomra.agents.orchestrator import ResearchOrchestrator
    from axiomra.data.repository import DataRepository
    from axiomra.decision import DecisionConfig, DecisionEngine
    from axiomra.execution.paper import PaperExecutionEngine
    from axiomra.fusion.engine import SignalFusionEngine
    from axiomra.pipeline import AxiomraPipeline, PipelineContext
    from axiomra.portfolio.optimizer import PortfolioConfig, PortfolioOptimizer
    from axiomra.quant.momentum import MomentumBaseline

    class NoopRepo(DataRepository):
        async def insert_bars(self, bars):
            return 0

        async def bars(self, symbol, start=None, end=None):
            return []

        async def save_decision(self, candidate, signals, proposal, risk, execution):
            return "id"

    from datetime import datetime

    from axiomra.domain.market import OHLCV, MarketSnapshot

    pipeline = AxiomraPipeline(
        decision_engine=DecisionEngine(
            quant_model=MomentumBaseline(),
            orchestrator=ResearchOrchestrator(agents=[]),
            fusion_engine=SignalFusionEngine(),
            config=DecisionConfig(no_trade_threshold=0.30),
        ),
        portfolio_engine=PortfolioOptimizer(
            config=PortfolioConfig(max_position_pct=0.03)
        ),
        risk_engine=RiskEngine(policy=RiskPolicy.defaults()),
        execution_engine=PaperExecutionEngine(),
        repository=NoopRepo(),
    )

    # Sector limit forces rejection: 16% projected sector > 15% cap.
    snapshot = MarketSnapshot(
        symbol="ABC",
        timestamp=datetime.now(UTC),
        bar=OHLCV(open=100, high=102, low=99, close=101, volume=1_000_000),
        features={
            "momentum_5d": 0.05,
            "momentum_20d": 0.15,
            "momentum_60d": 0.30,
            "volatility_20d": 0.02,
            "volume_ratio": 1.5,
            "distance_ema20": 0.03,
            "ret_1d": 0.01,
        },
        market_regime="TREND_UP",
        data_version="test-v1",
    )
    ctx = PipelineContext(entry_price=101, atr=2.0, portfolio_value=1_000_000)
    pipeline.portfolio.state.sector_exposure = {"UNKNOWN": 0.14}

    outcome = _run_async(pipeline.run(snapshot, ctx))

    assert outcome.status == "RISK_REJECTED"
    assert outcome.risk is not None
    assert outcome.risk.approved is False
    assert outcome.execution is None
    assert "SECTOR_LIMIT" in outcome.reasons


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)
