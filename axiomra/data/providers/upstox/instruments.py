"""Upstox BOD Instrument Master Provider."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from axiomra.data.instruments import Instrument, InstrumentMaster
from axiomra.data.providers.upstox.client import UpstoxClient
from axiomra.data.providers.upstox.models import UpstoxInstrumentItem
from axiomra.storage.raw import RawFetchManifest, RawStore


class UpstoxInstrumentProvider:
    """Parses Upstox BOD instrument master JSON into Axiomra InstrumentMaster."""

    def __init__(
        self,
        raw_store: RawStore | None = None,
        client: UpstoxClient | None = None,
    ) -> None:
        self.raw_store = raw_store or RawStore()
        self.client = client or UpstoxClient()
        self._key_to_id: dict[str, str] = {}
        self._symbol_to_key: dict[str, str] = {}

    def fetch_and_parse(
        self,
        mock_bytes: bytes | None = None,
        parser_version: str = "v1",
    ) -> tuple[InstrumentMaster, RawFetchManifest, dict[str, str], dict[str, str]]:
        """Fetch raw BOD JSON, persist raw bytes & manifest, parse into InstrumentMaster.

        Returns (instrument_master, fetch_manifest, key_to_id_map, symbol_to_key_map).
        """
        raw_bytes = self.client.fetch_bod_instruments_bytes(mock_bytes=mock_bytes)
        filename = f"NSE_BOD_{datetime.now(UTC).strftime('%Y%m%d')}.json"
        manifest = self.raw_store.put_raw(
            provider="upstox",
            resource_type="instruments",
            filename=filename,
            data=raw_bytes,
            parser_version=parser_version,
        )

        items_raw: list[dict[str, Any]] = json.loads(raw_bytes.decode("utf-8"))
        master = InstrumentMaster()
        key_map: dict[str, str] = {}
        symbol_map: dict[str, str] = {}

        for item_dict in items_raw:
            item = UpstoxInstrumentItem.model_validate(item_dict)
            # Filter for NSE Equity spot instruments only
            if item.exchange != "NSE":
                continue
            if item.instrument_type and item.instrument_type.upper() not in {"EQ", "EQUITY"}:
                continue

            symbol_raw = item.trading_symbol.strip()
            symbol_ns = symbol_raw if symbol_raw.endswith(".NS") else f"{symbol_raw}.NS"

            # Derive canonical instrument_id: ISIN-based if present
            if item.isin and item.isin.strip():
                instrument_id = f"inst-isin-{item.isin.strip()}"
            else:
                instrument_id = f"inst-upstox-{item.instrument_key.replace('|', '_')}"

            key_map[item.instrument_key] = instrument_id
            symbol_map[symbol_ns] = item.instrument_key
            symbol_map[symbol_raw] = item.instrument_key

            inst = Instrument(
                instrument_id=instrument_id,
                symbol=symbol_ns,
                exchange="NSE",
                isin=item.isin.strip() if item.isin else None,
                name=item.name.strip() if item.name else None,
                active_from=datetime(2000, 1, 1, tzinfo=UTC),
            )
            master.upsert(inst)

        self._key_to_id = key_map
        self._symbol_to_key = symbol_map
        return master, manifest, key_map, symbol_map

    def get_instrument_id(self, instrument_key: str) -> str | None:
        """Lookup canonical instrument_id for an Upstox instrument_key."""
        return self._key_to_id.get(instrument_key)

    def get_instrument_key(self, symbol: str) -> str | None:
        """Lookup Upstox instrument_key for a trading symbol (e.g. RELIANCE.NS)."""
        return self._symbol_to_key.get(symbol)
