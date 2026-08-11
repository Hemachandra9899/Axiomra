"""NSE CM-UDiFF Common Bhavcopy Final Provider."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from axiomra.data.instruments import InstrumentMaster
from axiomra.domain.market import Bar
from axiomra.storage.raw import RawFetchManifest, RawStore


class NSEBhavcopyProvider:
    """Parses NSE daily CM-UDiFF Bhavcopy files for EOD market data."""

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()

    def parse_bhavcopy_bytes(
        self,
        raw_bytes: bytes,
        trade_date: str,
        instruments: InstrumentMaster | None = None,
        universe_symbols: set[str] | None = None,
        parser_version: str = "v1",
    ) -> tuple[dict[str, Bar], RawFetchManifest]:
        """Parse raw NSE Bhavcopy CSV bytes into a dictionary of {symbol: Bar}.

        Saves raw bytes & manifest to `RawStore`. Filters for 'EQ' series and optional
        universe_symbols.
        """
        filename = f"bhavcopy_{trade_date}.csv"
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="bhavcopy",
            filename=filename,
            data=raw_bytes,
            request_parameters={"trade_date": trade_date},
            parser_version=parser_version,
        )

        content = raw_bytes.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(content))

        bars: dict[str, Bar] = {}

        for row in reader:
            # Handle variations in header naming (CM-UDiFF vs classic Bhavcopy)
            series = (row.get("SERIES") or row.get("SctySrs") or "").strip()
            if series not in {"EQ", "BE", ""}:
                continue

            raw_symbol = (row.get("SYMBOL") or row.get("TckrSymb") or row.get("TradSctyNm") or "").strip()
            if not raw_symbol:
                continue

            symbol_ns = raw_symbol if raw_symbol.endswith(".NS") else f"{raw_symbol}.NS"
            if universe_symbols and symbol_ns not in universe_symbols and raw_symbol not in universe_symbols:
                continue

            date_str = (row.get("TIMESTAMP") or row.get("TRDG_DT") or row.get("Date") or trade_date).strip()
            try:
                if "-" in date_str and len(date_str) == 10:
                    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                elif "-" in date_str:
                    dt = datetime.strptime(date_str, "%d-%b-%Y").replace(tzinfo=UTC)
                else:
                    dt = datetime.strptime(trade_date, "%Y%m%d").replace(tzinfo=UTC)
            except Exception:
                dt = datetime.strptime(trade_date, "%Y%m%d").replace(tzinfo=UTC)

            def _flt(col_names: list[str]) -> float:
                for col in col_names:
                    val = row.get(col)
                    if val is not None and val.strip():
                        try:
                            return float(val.strip().replace(",", ""))
                        except ValueError:
                            pass
                return 0.0

            open_p = _flt(["OPEN_PRICE", "OPEN", "OpnPrc"])
            high_p = _flt(["HIGH_PRICE", "HIGH", "HghPrc"])
            low_p = _flt(["LOW_PRICE", "LOW", "LwPrc"])
            close_p = _flt(["CLOSE_PRICE", "CLOSE", "ClsPrc"])
            vol = _flt(["TTL_TRD_QTY", "TOTTRDQTY", "TtlTradgVol", "VOLUME"])

            bar = Bar(
                symbol=symbol_ns,
                timestamp=dt,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol,
            )
            bars[symbol_ns] = bar

        return bars, manifest
