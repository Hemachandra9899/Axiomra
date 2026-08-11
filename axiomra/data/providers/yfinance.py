"""yfinance market data provider.

Optional dependency: `pip install "axiomra[data]"` (yfinance). The provider
only imports yfinance lazily so the core package never depends on it.
"""

from __future__ import annotations

from datetime import UTC, date

from axiomra.data.providers.base import MarketDataProvider
from axiomra.domain.common import as_utc
from axiomra.domain.market import OHLCV, Bar, MarketSnapshot


class YFinanceProvider(MarketDataProvider):
    """Reads daily OHLCV bars through yfinance."""

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: PLC0415

            self._yf = yfinance
        except ImportError as exc:  # pragma: no cover - exercised in CI without dep
            raise ImportError(
                "yfinance not installed; run `pip install 'axiomra[data]'`"
            ) from exc

    async def bars(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1d",
    ) -> list[Bar]:
        frame = self._yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval=timeframe,
            auto_adjust=False,
        )
        result: list[Bar] = []
        for idx, row in frame.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            result.append(
                Bar(
                    symbol=symbol,
                    timestamp=as_utc(ts),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        return result

    async def latest_snapshot(self, symbol: str) -> MarketSnapshot:
        frame = self._yf.Ticker(symbol).history(
            period="5d", interval="1d", auto_adjust=False
        )
        if frame.empty:
            raise LookupError(f"no data for {symbol}")
        last = frame.iloc[-1]
        ts = frame.index[-1].to_pydatetime()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return MarketSnapshot(
            symbol=symbol,
            timestamp=as_utc(ts),
            bar=OHLCV(
                open=float(last["Open"]),
                high=float(last["High"]),
                low=float(last["Low"]),
                close=float(last["Close"]),
                volume=float(last["Volume"]),
            ),
            data_version="yf-latest",
        )
