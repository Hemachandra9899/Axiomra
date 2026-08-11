"""Immutable context evaluated by Axiomra Guard.

All values are snapshots of portfolio and market state at evaluation time.
The risk engine never fetches data itself; it judges the context it is given.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from axiomra.domain.portfolio import PortfolioProposal


class RiskContext(BaseModel):
    """Everything the risk engine needs to know for one proposal."""

    portfolio_value: float = Field(gt=0)
    daily_pnl_pct: float = Field(default=0.0)
    drawdown_pct: float = Field(default=0.0)
    position_count: int = Field(default=0, ge=0)

    current_position_pct: float = Field(default=0.0, ge=0.0)
    projected_position_pct: float = Field(default=0.0, ge=0.0)

    current_sector_pct: float = Field(default=0.0, ge=0.0)
    projected_sector_pct: float = Field(default=0.0, ge=0.0)

    projected_correlation_pct: float = Field(default=0.0, ge=0.0)

    liquidity_ok: bool = True
    data_fresh: bool = True
    event_risk: bool = False

    @classmethod
    def from_proposal(
        cls,
        proposal: PortfolioProposal,
        *,
        daily_pnl_pct: float = 0.0,
        drawdown_pct: float = 0.0,
        liquidity_ok: bool = True,
        data_fresh: bool = True,
        event_risk: bool = False,
    ) -> RiskContext:
        return cls(
            portfolio_value=proposal.portfolio_value,
            daily_pnl_pct=daily_pnl_pct,
            drawdown_pct=drawdown_pct,
            current_position_pct=proposal.current_position_pct,
            projected_position_pct=proposal.projected_position_pct,
            current_sector_pct=max(0.0, proposal.projected_sector_pct - proposal.target_weight),
            projected_sector_pct=proposal.projected_sector_pct,
            projected_correlation_pct=proposal.projected_correlation_pct,
            liquidity_ok=liquidity_ok,
            data_fresh=data_fresh,
            event_risk=event_risk,
        )
