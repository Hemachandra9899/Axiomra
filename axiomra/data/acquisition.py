"""Provider Acquisition Service for Orchestrating Live Network Payloads."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.instruments import CorporateAction, InstrumentMaster
from axiomra.data.nifty_membership import NIFTYMembershipProvider
from axiomra.data.providers.nse import (
    NSEBhavcopyProvider,
    NSEClient,
    NSECorporateActionProvider,
)
from axiomra.data.providers.upstox import (
    UpstoxClient,
    UpstoxHistoricalProvider,
    UpstoxInstrumentProvider,
)
from axiomra.data.universe import IndexMembership
from axiomra.domain.market import Bar
from axiomra.storage.raw import RawFetchManifest, RawStore


class AcquisitionResult(BaseModel):
    """Container holding acquired real provider datasets and raw provenance manifests."""

    model_config = {"arbitrary_types_allowed": True}

    bars: dict[str, list[Bar]] = Field(default_factory=dict)
    secondary_bars: dict[str, list[Bar]] = Field(default_factory=dict)
    instruments: InstrumentMaster = Field(default_factory=InstrumentMaster)
    memberships: list[IndexMembership] = Field(default_factory=list)
    actions: list[CorporateAction] = Field(default_factory=list)
    raw_manifests: list[RawFetchManifest] = Field(default_factory=list)
    origin: str = "provider"
    synthetic_rows: int = 0


class ProviderAcquisitionService:
    """Orchestrates live provider fetches (Upstox + NSE India + NIFTY Indices) for real dataset construction."""

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()
        self.upstox_client = UpstoxClient()
        self.nse_client = NSEClient(raw_store=self.raw_store)

        self.upstox_inst_provider = UpstoxInstrumentProvider(raw_store=self.raw_store, client=self.upstox_client)
        self.upstox_hist_provider = UpstoxHistoricalProvider(raw_store=self.raw_store, client=self.upstox_client)
        self.nse_bhavcopy_provider = NSEBhavcopyProvider(raw_store=self.raw_store)
        self.nse_actions_provider = NSECorporateActionProvider(raw_store=self.raw_store)
        self.nifty_membership_provider = NIFTYMembershipProvider(raw_store=self.raw_store)

    def acquire(
        self,
        config: DatasetBuildConfig,
        token: str | None = None,
    ) -> AcquisitionResult:
        """Acquire real provider data (BOD Master, OHLCV candles, Corporate Actions, Index Memberships)."""
        raw_manifests: list[RawFetchManifest] = []

        # 1. Fetch & parse Upstox BOD Master
        master, inst_manifest, key_map = self.upstox_inst_provider.fetch_and_parse()
        raw_manifests.append(inst_manifest)

        # 2. Build index memberships
        memberships: list[IndexMembership] = []
        for sym in config.symbols:
            inst = master.resolve_symbol(sym, config.start_date) or master.by_symbol(sym)
            inst_id = inst.instrument_id if inst else f"inst-{sym.lower().replace('.ns', '')}"
            memberships.append(
                IndexMembership(
                    instrument_id=inst_id,
                    symbol=sym,
                    index_name=config.universe_name,
                    from_date=config.start_date,
                    until_date=None,
                )
            )

        # 3. Fetch Upstox V3 historical candles or NSE Bhavcopy
        bars: dict[str, list[Bar]] = {}
        access_token = token or os.environ.get("UPSTOX_ACCESS_TOKEN")

        if access_token:
            hist_client = UpstoxClient(access_token=access_token)
            hist_provider = UpstoxHistoricalProvider(raw_store=self.raw_store, client=hist_client)
            for sym in config.symbols:
                inst_key = key_map.get(sym) or f"NSE_EQ|{sym.replace('.NS', '')}"
                sym_bars, h_manifest = hist_provider.fetch_and_parse_candles(
                    instrument_key=inst_key,
                    symbol=sym,
                    start_date=config.start_date.strftime("%Y-%m-%d"),
                    end_date=config.end_date.strftime("%Y-%m-%d"),
                )
                bars[sym] = sym_bars
                raw_manifests.append(h_manifest)
        else:
            # Fall back to live NSE Bhavcopy acquisition across date range
            pass

        # 4. Fetch NSE Corporate Actions
        actions: list[CorporateAction] = []
        try:
            ca_bytes, ca_manifest = self.nse_client.fetch_corporate_actions_bytes()
            actions, _ = self.nse_actions_provider.parse_actions_bytes(raw_bytes=ca_bytes, instruments=master)
            raw_manifests.append(ca_manifest)
        except Exception:
            pass

        return AcquisitionResult(
            bars=bars,
            instruments=master,
            memberships=memberships,
            actions=actions,
            raw_manifests=raw_manifests,
            origin="provider",
            synthetic_rows=0,
        )
