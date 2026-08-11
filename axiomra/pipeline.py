"""End-to-end Axiomra pipeline runner.

This is the only code path that creates orders and submits them. It enforces
the dependency chain in code:

    Decision -> Portfolio -> Guard -> Execution -> Journal
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from axiomra.data.repository import DataRepository
from axiomra.decision import DecisionEngine, DecisionResult
from axiomra.domain.market import MarketSnapshot
from axiomra.domain.orders import ExecutionResult
from axiomra.domain.portfolio import PortfolioProposal
from axiomra.execution.base import ExecutionEngine
from axiomra.portfolio.optimizer import PortfolioOptimizer
from axiomra.portfolio.planner import plan_order
from axiomra.risk.context import RiskContext
from axiomra.risk.engine import RiskDecision, RiskEngine


class PipelineOutcome(BaseModel):
    status: str
    symbol: str
    decision: DecisionResult | None = None
    proposal: PortfolioProposal | None = None
    risk: RiskDecision | None = None
    execution: ExecutionResult | None = None
    reasons: list[str] = Field(default_factory=list)



@dataclass
class PipelineContext:
    """Market state needed to turn a candidate into a proposal."""

    entry_price: float
    atr: float
    portfolio_value: float
    daily_pnl_pct: float = 0.0
    drawdown_pct: float = 0.0
    liquidity_ok: bool = True
    data_fresh: bool = True
    event_risk: bool = False
    position_count: int = 0


class AxiomraPipeline:
    """Composes decision, portfolio, risk and execution in order."""

    def __init__(
        self,
        decision_engine: DecisionEngine,
        portfolio_engine: PortfolioOptimizer,
        risk_engine: RiskEngine,
        execution_engine: ExecutionEngine,
        repository: DataRepository,
    ) -> None:
        self.decisions = decision_engine
        self.portfolio = portfolio_engine
        self.risk = risk_engine
        self.execution = execution_engine
        self.repository = repository

    async def run(
        self,
        snapshot: MarketSnapshot,
        ctx: PipelineContext,
    ) -> PipelineOutcome:
        decision = await self.decisions.analyze(snapshot)

        if decision.action == "NO_TRADE" or decision.candidate is None:
            outcome = PipelineOutcome(
                status="NO_TRADE",
                symbol=snapshot.symbol,
                decision=decision,
            )
            await self.repository.save_decision(
                candidate=decision.candidate,
                signals=decision.evidence,
                proposal=None,
                risk=None,
                execution=None,
            ) if decision.candidate else None
            return outcome

        proposal = self.portfolio.propose(
            candidate=decision.candidate,
            portfolio_value=ctx.portfolio_value,
            entry_price=ctx.entry_price,
            atr=ctx.atr,
        )

        risk_ctx = RiskContext(
            portfolio_value=ctx.portfolio_value,
            daily_pnl_pct=ctx.daily_pnl_pct,
            drawdown_pct=ctx.drawdown_pct,
            position_count=ctx.position_count,
            current_position_pct=proposal.current_position_pct,
            projected_position_pct=proposal.projected_position_pct,
            projected_sector_pct=proposal.projected_sector_pct,
            projected_correlation_pct=proposal.projected_correlation_pct,
            liquidity_ok=ctx.liquidity_ok,
            data_fresh=ctx.data_fresh,
            event_risk=ctx.event_risk,
        )
        risk = self.risk.evaluate(risk_ctx)

        if not risk.approved:
            outcome = PipelineOutcome(
                status="RISK_REJECTED",
                symbol=snapshot.symbol,
                decision=decision,
                proposal=proposal,
                risk=risk,
                reasons=risk.reasons,
            )
            await self.repository.save_decision(
                candidate=decision.candidate,
                signals=decision.evidence,
                proposal=proposal,
                risk=risk,
                execution=None,
            )
            return outcome

        # The order comes from the current->target delta, never the action
        # label. A REDUCE on a zero position yields no order; a LONG whose
        # target is already reached yields no order.
        order = plan_order(
            symbol=snapshot.symbol,
            action=decision.action,
            current_quantity=proposal.current_quantity,
            target_quantity=proposal.target_quantity,
            decision_id=getattr(decision.candidate, "decision_id", None),
        )
        if order is None:
            outcome = PipelineOutcome(
                status="NO_TRADE",
                symbol=snapshot.symbol,
                decision=decision,
                proposal=proposal,
                risk=risk,
                reasons=["current position already at target"],
            )
            await self.repository.save_decision(
                candidate=decision.candidate,
                signals=decision.evidence,
                proposal=proposal,
                risk=risk,
                execution=None,
            )
            return outcome

        execution = await self.execution.submit(order)

        await self.repository.save_decision(
            candidate=decision.candidate,
            signals=decision.evidence,
            proposal=proposal,
            risk=risk,
            execution=execution,
        )

        return PipelineOutcome(
            status="EXECUTED" if execution.is_filled else "EXECUTION_FAILED",
            symbol=snapshot.symbol,
            decision=decision,
            proposal=proposal,
            risk=risk,
            execution=execution,
        )
