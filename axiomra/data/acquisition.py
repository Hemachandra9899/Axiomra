"""Provider Acquisition Service for Orchestrating Live Network Payloads."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.builder.errors import (
    CorporateActionFetchError,
    InstrumentResolutionFailedError,
    MissingProviderCredentialsError,
)
from axiomra.data.ingestion import adjust_splits
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
from axiomra.data.snapshot import AdjustmentMode
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
        access_token = token or os.environ.get("UPSTOX_ACCESS_TOKEN")
        if not access_token:
            raise MissingProviderCredentialsError(
                "UPSTOX_ACCESS_TOKEN environment variable or token parameter is required for provider data acquisition."
            )

        raw_manifests: list[RawFetchManifest] = []

        # 1. Fetch & parse Upstox BOD Master with explicit symbol_map
        master, inst_manifest, key_map, symbol_map = self.upstox_inst_provider.fetch_and_parse()
        raw_manifests.append(inst_manifest)

        # 2. Build Index Memberships with zero manufactured synthetic IDs
        memberships: list[IndexMembership] = []
        for sym in config.symbols:
            inst = master.resolve_symbol(sym, config.start_date) or master.by_symbol(sym)
            if inst is None:
                raise InstrumentResolutionFailedError(
                    f"Cannot resolve canonical instrument_id for '{sym}' in Upstox InstrumentMaster."
                )
            memberships.append(
                IndexMembership(
                    instrument_id=inst.instrument_id,
                    symbol=sym,
                    index_name=config.universe_name,
                    from_date=config.start_date,
                    until_date=None,
                )
            )

        # 3. Fetch Upstox V3 Historical Daily OHLCV Candles
        hist_client = UpstoxClient(access_token=access_token)
        hist_provider = UpstoxHistoricalProvider(raw_store=self.raw_store, client=hist_client)
        raw_bars: dict[str, list[Bar]] = {}

        for sym in config.symbols:
            inst_key = symbol_map.get(sym) or symbol_map.get(sym.replace(".NS", ""))
            if not inst_key:
                raise InstrumentResolutionFailedError(
                    f"No Upstox provider instrument_key mapping found for trading symbol '{sym}'."
                )
            sym_bars, h_manifest = hist_provider.fetch_and_parse_candles(
                instrument_key=inst_key,
                symbol=sym,
                start_date=config.start_date.strftime("%Y-%m-%d"),
                end_date=config.end_date.strftime("%Y-%m-%d"),
            )
            raw_bars[sym] = sym_bars
            raw_manifests.append(h_manifest)

        # 4. Fetch & Parse NSE Corporate Actions (Raise on failure for SPLIT_ADJUSTED datasets)
        actions: list[CorporateAction] = []
        try:
            ca_bytes, ca_manifest = self.nse_client.fetch_corporate_actions_bytes()
            actions, _ = self.nse_actions_provider.parse_actions_bytes(raw_bytes=ca_bytes, instruments=master)
            raw_manifests.append(ca_manifest)
        except Exception as err:
            if config.adjustment_mode != AdjustmentMode.RAW:
                raise CorporateActionFetchError(
                    f"Corporate action acquisition failed for {config.adjustment_mode.value} dataset: {err}"
                ) from err

        # 5. Apply Axiomra-Owned Corporate Action Adjustment Transformation
        adjusted_bars: dict[str, list[Bar]] = {}
        for sym, b_list in raw_bars.items():
            sym_actions = [a for a in actions if a.instrument_id == master.resolve_symbol(sym).instrument_id]
            sym_adj, _ = adjust_splits(
                bars=b_list,
                actions=sym_actions,
                adjustment_mode=config.adjustment_mode,
            )
            adjusted_bars[sym] = sym_adj

        return AcquisitionResult(
            bars=adjusted_bars,
            instruments=master,
            memberships=memberships,
            actions=actions,
            raw_manifests=raw_manifests,
            origin="provider",
            synthetic_rows=0,
        )
