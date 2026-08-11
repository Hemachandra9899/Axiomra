"""Reconstructed NIFTY Index Membership Provider with explicit provenance tracking."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from axiomra.data.universe import IndexMembership
from axiomra.storage.raw import RawFetchManifest, RawStore


class ReconstructedMembershipRecord(BaseModel):
    """Membership record with full audit provenance."""

    index_name: str
    instrument_id: str
    symbol: str
    valid_from: datetime
    valid_until: datetime | None = None
    source: str = "NSE Indices reconstitution notices & constituent snapshots"
    source_date: datetime
    source_reference: str
    reconstruction_version: str = "nifty200-reconstructed-v1"


class NIFTYMembershipProvider:
    """Builds and manages point-in-time IndexMembership intervals with reconstruction provenance."""

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()

    def parse_membership_source_bytes(
        self,
        raw_bytes: bytes,
        index_name: str = "NIFTY 200",
        source_reference: str = "official_reconstitution_history_v1",
        reconstruction_version: str = "nifty200-reconstructed-v1",
        parser_version: str = "v1",
    ) -> tuple[list[IndexMembership], list[ReconstructedMembershipRecord], RawFetchManifest]:
        """Parse raw membership constituent JSON bytes into IndexMembership list and detailed records."""
        filename = f"membership_{index_name.lower().replace(' ', '_')}_{reconstruction_version}.json"
        manifest = self.raw_store.put_raw(
            provider="nifty_indices",
            resource_type="membership_sources",
            filename=filename,
            data=raw_bytes,
            request_parameters={
                "index_name": index_name,
                "reconstruction_version": reconstruction_version,
                "source_reference": source_reference,
            },
            parser_version=parser_version,
        )

        raw_list: list[dict[str, Any]] = json.loads(raw_bytes.decode("utf-8"))
        index_memberships: list[IndexMembership] = []
        provenance_records: list[ReconstructedMembershipRecord] = []

        now_utc = datetime.now(UTC)

        for item in raw_list:
            symbol = str(item["symbol"]).strip()
            symbol_ns = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            instrument_id = str(item.get("instrument_id") or f"inst-nse-{symbol.replace('.NS', '')}").strip()

            from_dt = datetime.fromisoformat(str(item["from_date"])) if "from_date" in item else datetime(2017, 1, 1, tzinfo=UTC)
            until_dt = datetime.fromisoformat(str(item["until_date"])) if item.get("until_date") else None

            if from_dt.tzinfo is None:
                from_dt = from_dt.replace(tzinfo=UTC)
            if until_dt is not None and until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=UTC)

            mem = IndexMembership(
                instrument_id=instrument_id,
                symbol=symbol_ns,
                index_name=index_name,
                from_date=from_dt,
                until_date=until_dt,
            )
            index_memberships.append(mem)

            rec = ReconstructedMembershipRecord(
                index_name=index_name,
                instrument_id=instrument_id,
                symbol=symbol_ns,
                valid_from=from_dt,
                valid_until=until_dt,
                source="NSE Indices reconstitution notices & constituent snapshots",
                source_date=now_utc,
                source_reference=source_reference,
                reconstruction_version=reconstruction_version,
            )
            provenance_records.append(rec)

        return index_memberships, provenance_records, manifest
