"""Portfolio construction from ranked candidates.

Deterministic rules, no LLM in the loop:

    max individual position
    max sector exposure
    max correlated cluster

A proposal expresses a *target position*. The execution planner derives the
order from the delta between current and target, so a REDUCE can never
become a BUY. For V1 long-only, REDUCE means "target zero (exit)".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from axiomra.domain.portfolio import (
    PortfolioProposal,
    PositionSize,
    ProposalDirection,
)
from axiomra.domain.signals import TradeCandidate
from axiomra.portfolio.sizing import (
    PositionSizeRequest,
    apply_position_cap,
    calculate_quantity,
)


@dataclass
class PortfolioConfig:
    max_position_pct: float = 0.03
    max_sector_pct: float = 0.15
    max_correlated_pct: float = 0.20
    risk_fraction: float = 0.005
    atr_multiplier: float = 2.0
    min_weight: float = 0.0
    sector_of: dict[str, str] = field(default_factory=dict)

    def sector_for(self, symbol: str) -> str:
        return self.sector_of.get(symbol, "UNKNOWN")


@dataclass
class PortfolioState:
    """Existing book used to compute concentration deltas."""

    holdings: dict[str, float] = field(default_factory=dict)
    quantities: dict[str, int] = field(default_factory=dict)
    sector_exposure: dict[str, float] = field(default_factory=dict)

    def quantity(self, symbol: str) -> int:
        return self.quantities.get(symbol, 0)


class PortfolioOptimizer:
    """Converts ranked candidates into target-position proposals."""

    def __init__(
        self,
        config: PortfolioConfig | None = None,
        state: PortfolioState | None = None,
    ) -> None:
        self.config = config or PortfolioConfig()
        self.state = state or PortfolioState()

    def propose(
        self,
        candidate: TradeCandidate,
        portfolio_value: float,
        entry_price: float,
        atr: float,
    ) -> PortfolioProposal:
        """Build a target-position proposal for one candidate.

        - LONG   -> target = risk-based size (bounded by position cap).
                    If the current position already covers the target, the
                    delta is <= 0 and the planner emits no order.
        - REDUCE -> target = 0 (exit). Zero position yields no order.
        """
        current_quantity = self.state.quantity(candidate.symbol)
        current_pct = self.state.holdings.get(candidate.symbol, 0.0)

        if candidate.direction != "LONG":
            return PortfolioProposal(
                symbol=candidate.symbol,
                portfolio_value=portfolio_value,
                direction=ProposalDirection.REDUCE,
                target_weight=0.0,
                current_quantity=current_quantity,
                target_quantity=0,
                current_position_pct=current_pct,
                projected_position_pct=0.0,
                projected_sector_pct=0.0,
                reasons=["bearish signal: target position is zero (exit)"],
            )

        req = PositionSizeRequest(
            portfolio_value=portfolio_value,
            entry_price=entry_price,
            atr=atr,
            risk_fraction=self.config.risk_fraction,
            atr_multiplier=self.config.atr_multiplier,
        )
        risk_qty = calculate_quantity(req)
        capped_qty = apply_position_cap(
            risk_qty, entry_price, portfolio_value, self.config.max_position_pct
        )

        if capped_qty <= 0:
            return self._empty_long(candidate, portfolio_value, current_quantity, current_pct)

        notional = capped_qty * entry_price
        target_weight = notional / portfolio_value
        stop = entry_price - self.config.atr_multiplier * atr
        risk_budget = portfolio_value * self.config.risk_fraction

        sector = self.config.sector_for(candidate.symbol)
        projected_sector = self.state.sector_exposure.get(sector, 0.0) + target_weight

        return PortfolioProposal(
            symbol=candidate.symbol,
            portfolio_value=portfolio_value,
            direction=ProposalDirection.LONG,
            position_size=PositionSize(
                symbol=candidate.symbol,
                quantity=capped_qty,
                notional=notional,
                target_weight=target_weight,
                stop_price=stop,
                risk_budget=risk_budget,
                reason="risk-based sizing with position cap",
            ),
            target_weight=target_weight,
            current_quantity=current_quantity,
            target_quantity=capped_qty,
            current_position_pct=current_pct,
            projected_position_pct=target_weight,
            projected_sector_pct=projected_sector,
            reasons=[
                f"current={current_quantity} target={capped_qty}",
                f"target_weight={target_weight:.2%}",
                f"stop={stop:.2f}",
            ],
        )

    def _empty_long(
        self,
        candidate: TradeCandidate,
        portfolio_value: float,
        current_quantity: int,
        current_pct: float,
    ) -> PortfolioProposal:
        return PortfolioProposal(
            symbol=candidate.symbol,
            portfolio_value=portfolio_value,
            direction=ProposalDirection.LONG,
            target_weight=0.0,
            current_quantity=current_quantity,
            target_quantity=0,
            current_position_pct=current_pct,
            projected_position_pct=0.0,
            projected_sector_pct=0.0,
            reasons=["size rounded to zero"],
        )
