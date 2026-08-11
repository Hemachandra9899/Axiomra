"""Research endpoints.

POST /v1/research/{symbol} produces a DecisionResult — research only. It
never places orders.
"""

from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter

from axiomra.decision import DecisionEngine

router = APIRouter(prefix="/v1", tags=["research"])

# Set by the app factory; moved into dependencies.py for a real deployment.
_decision_engine: DecisionEngine | None = None


def configure(engine: DecisionEngine) -> None:
    global _decision_engine
    _decision_engine = engine


@router.post("/research/{symbol}")
async def research_symbol(symbol: str) -> dict[str, object]:
    if _decision_engine is None:
        return {"status": "NOT_CONFIGURED", "symbol": symbol}
    snapshot = await _snapshot_for(symbol)
    result = await _decision_engine.analyze(snapshot)
    return result.model_dump()


async def _snapshot_for(symbol: str):  # pragma: no cover - needs a provider
    from datetime import datetime

    from axiomra.domain.market import OHLCV, MarketSnapshot
    from axiomra.domain.signals import Regime

    return MarketSnapshot(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        bar=OHLCV(open=100, high=105, low=99, close=102, volume=1_000_000),
        market_regime=Regime.UNKNOWN,
        data_version="placeholder",
    )
