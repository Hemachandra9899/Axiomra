"""Independent risk rules.

The thresholds below are example research defaults — NOT universal financial
rules. Set actual policy before any live use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from axiomra.domain.portfolio import RiskCheck
from axiomra.risk.context import RiskContext


class RiskRule(ABC):
    """One deterministic, independently testable rule."""

    name = "base"

    @abstractmethod
    def check(self, ctx: RiskContext) -> RiskCheck: ...


class DataFreshnessRule(RiskRule):
    name = "DATA_FRESHNESS"

    def check(self, ctx: RiskContext) -> RiskCheck:
        return RiskCheck(
            name=self.name,
            passed=ctx.data_fresh,
            reason=None if ctx.data_fresh else "STALE_DATA",
        )


class LiquidityRule(RiskRule):
    name = "LIQUIDITY"

    def check(self, ctx: RiskContext) -> RiskCheck:
        return RiskCheck(
            name=self.name,
            passed=ctx.liquidity_ok,
            reason=None if ctx.liquidity_ok else "INSUFFICIENT_LIQUIDITY",
        )


@dataclass
class PositionLimitRule(RiskRule):
    max_position_pct: float = 0.03

    def check(self, ctx: RiskContext) -> RiskCheck:
        ok = ctx.projected_position_pct <= self.max_position_pct
        return RiskCheck(
            name=self.name,
            passed=ok,
            reason=None if ok else "POSITION_LIMIT",
            metadata={"projected_position_pct": ctx.projected_position_pct},
        )


@dataclass
class SectorLimitRule(RiskRule):
    max_sector_pct: float = 0.15

    def check(self, ctx: RiskContext) -> RiskCheck:
        ok = ctx.projected_sector_pct <= self.max_sector_pct
        return RiskCheck(
            name=self.name,
            passed=ok,
            reason=None if ok else "SECTOR_LIMIT",
            metadata={"projected_sector_pct": ctx.projected_sector_pct},
        )


@dataclass
class CorrelationLimitRule(RiskRule):
    max_correlation_pct: float = 0.20

    def check(self, ctx: RiskContext) -> RiskCheck:
        ok = ctx.projected_correlation_pct <= self.max_correlation_pct
        return RiskCheck(
            name=self.name,
            passed=ok,
            reason=None if ok else "CORRELATION_LIMIT",
            metadata={"projected_correlation_pct": ctx.projected_correlation_pct},
        )


@dataclass
class DailyLossLimitRule(RiskRule):
    max_daily_loss_pct: float = -0.01

    def check(self, ctx: RiskContext) -> RiskCheck:
        ok = ctx.daily_pnl_pct > self.max_daily_loss_pct
        return RiskCheck(
            name=self.name,
            passed=ok,
            reason=None if ok else "DAILY_LOSS_LIMIT",
            metadata={"daily_pnl_pct": ctx.daily_pnl_pct},
        )


@dataclass
class DrawdownLimitRule(RiskRule):
    max_drawdown_pct: float = -0.10

    def check(self, ctx: RiskContext) -> RiskCheck:
        ok = ctx.drawdown_pct > self.max_drawdown_pct
        return RiskCheck(
            name=self.name,
            passed=ok,
            reason=None if ok else "PORTFOLIO_DRAWDOWN",
            metadata={"drawdown_pct": ctx.drawdown_pct},
        )


class EventRiskRule(RiskRule):
    name = "EVENT_RISK"

    def check(self, ctx: RiskContext) -> RiskCheck:
        return RiskCheck(
            name=self.name,
            passed=not ctx.event_risk,
            reason=None if not ctx.event_risk else "EVENT_RISK",
        )


@dataclass
class PositionCountRule(RiskRule):
    max_positions: int = 20

    def check(self, ctx: RiskContext) -> RiskCheck:
        ok = ctx.position_count < self.max_positions
        return RiskCheck(
            name=self.name,
            passed=ok,
            reason=None if ok else "POSITION_COUNT",
            metadata={"position_count": ctx.position_count},
        )


def compile_rules(
    *,
    max_position_pct: float = 0.03,
    max_sector_pct: float = 0.15,
    max_correlation_pct: float = 0.20,
    max_daily_loss_pct: float = -0.01,
    max_drawdown_pct: float = -0.10,
    max_positions: int = 20,
) -> list[RiskRule]:
    """Default rule set for the V1 cash-equity product."""
    return [
        DataFreshnessRule(),
        LiquidityRule(),
        PositionLimitRule(max_position_pct=max_position_pct),
        SectorLimitRule(max_sector_pct=max_sector_pct),
        CorrelationLimitRule(max_correlation_pct=max_correlation_pct),
        DailyLossLimitRule(max_daily_loss_pct=max_daily_loss_pct),
        DrawdownLimitRule(max_drawdown_pct=max_drawdown_pct),
        EventRiskRule(),
        PositionCountRule(max_positions=max_positions),
    ]
