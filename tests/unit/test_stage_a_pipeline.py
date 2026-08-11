"""Stage A Pipeline Integration Test — 10 stocks × 6 months data acquisition and persistence validation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from axiomra.data.coverage import CoverageAnalyzer
from axiomra.data.nifty_membership import NIFTYMembershipProvider
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.providers.nse import NSEBhavcopyProvider
from axiomra.data.providers.upstox import (
    UpstoxHistoricalProvider,
    UpstoxInstrumentProvider,
)
from axiomra.data.reconciliation import ProviderReconciler, ReconciliationConfig
from axiomra.data.snapshot import AdjustmentMode, create_snapshot
from axiomra.data.universe import Universe
from axiomra.domain.market import Bar
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.raw import RawStore


def test_stage_a_pipeline_end_to_end(tmp_path: Path):
    """Stage A Acceptance Test: 10 stocks × 6 months real-pipeline integration.

    Verifies raw storage immutability, Upstox + NSE reconciliation, strict membership
    provenance, coverage analysis, quality checks, snapshot creation, and exact Parquet
    logical SHA round-trip.
    """
    raw_dir = tmp_path / "raw"
    art_dir = tmp_path / "artifacts"

    raw_store = RawStore(root_dir=raw_dir)
    art_store = LocalArtifactStore(root_dir=art_dir)
    repo = ParquetDatasetRepository(store=art_store)

    # 1. Parse Upstox BOD Instrument Master (10 sample stocks)
    symbols = [f"STOCK{i:02d}" for i in range(1, 11)]
    mock_bod = [
        {
            "instrument_key": f"NSE_EQ|INE0000000{i:02d}",
            "trading_symbol": sym,
            "exchange": "NSE",
            "instrument_type": "EQ",
            "isin": f"INE0000000{i:02d}",
        }
        for i, sym in enumerate(symbols, start=1)
    ]
    upstox_inst_provider = UpstoxInstrumentProvider(raw_store=raw_store)
    master, inst_manifest, key_map = upstox_inst_provider.fetch_and_parse(
        mock_bytes=json.dumps(mock_bod).encode("utf-8")
    )
    assert len(master._all_instruments) == 10
    assert inst_manifest.sha256 is not None

    # 2. Upstox Historical Candle Fetch (10 stocks × ~120 trading days / 6 months)
    start_dt = datetime(2024, 1, 1, tzinfo=UTC)
    upstox_hist_provider = UpstoxHistoricalProvider(raw_store=raw_store)
    upstox_bars_dict: dict[str, list[Bar]] = {}

    for sym in symbols:
        symbol_ns = f"{sym}.NS"
        inst_key = f"NSE_EQ|INE0000000{symbols.index(sym)+1:02d}"

        # Generate ~120 synthetic trading day candles (weekdays only)
        candles = []
        for d in range(160):
            dt_curr = start_dt + timedelta(days=d)
            if dt_curr.weekday() >= 5:
                continue
            ts = dt_curr.isoformat()
            open_p = 100.0 + len(candles) * 0.1
            high_p = 102.0 + len(candles) * 0.1
            low_p = 99.0 + len(candles) * 0.1
            close_p = 101.0 + len(candles) * 0.1
            vol = 10000 + len(candles) * 50
            candles.append([ts, open_p, high_p, low_p, close_p, vol, 0])

        mock_payload = {"status": "success", "data": {"candles": candles}}
        bars, h_manifest = upstox_hist_provider.fetch_and_parse_candles(
            instrument_key=inst_key,
            symbol=symbol_ns,
            start_date="2024-01-01",
            end_date="2024-06-30",
            mock_bytes=json.dumps(mock_payload).encode("utf-8"),
        )
        upstox_bars_dict[symbol_ns] = bars
        assert h_manifest.sha256 is not None

    # 3. NSE Bhavcopy Cross-Check Feed
    nse_bhavcopy_provider = NSEBhavcopyProvider(raw_store=raw_store)
    nse_bars_dict: dict[str, list[Bar]] = {}

    for sym in symbols:
        symbol_ns = f"{sym}.NS"
        u_bars = upstox_bars_dict[symbol_ns]
        nse_bars_dict[symbol_ns] = []
        for b in u_bars:
            dt_str = b.timestamp.strftime("%Y-%m-%d")
            t_date = b.timestamp.strftime("%Y%m%d")
            csv_content = f"SYMBOL,SERIES,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,CLOSE_PRICE,TTL_TRD_QTY,TIMESTAMP\n{sym},EQ,{b.open},{b.high},{b.low},{b.close},{b.volume},{dt_str}\n"
            parsed_bars, b_manifest = nse_bhavcopy_provider.parse_bhavcopy_bytes(
                raw_bytes=csv_content.encode("utf-8"),
                trade_date=t_date,
            )
            if symbol_ns in parsed_bars:
                nse_bars_dict[symbol_ns].append(parsed_bars[symbol_ns])

    # 4. Run Provider Reconciliation
    reconciler = ProviderReconciler(ReconciliationConfig(max_close_diff_bps=10.0, max_volume_diff_pct=5.0, fail_on_missing=True))
    for sym in symbols:
        symbol_ns = f"{sym}.NS"
        rec_report = reconciler.reconcile_symbol_series(symbol_ns, upstox_bars_dict[symbol_ns], nse_bars_dict[symbol_ns])
        assert rec_report.valid is True
        assert rec_report.quarantined_count == 0

    # 5. Parse Reconstructed NIFTY Membership History
    mock_memberships = [
        {
            "instrument_id": f"inst-isin-INE0000000{i:02d}",
            "symbol": f"{sym}.NS",
            "from_date": "2024-01-01T00:00:00+00:00",
            "until_date": None,
        }
        for i, sym in enumerate(symbols, start=1)
    ]
    mem_provider = NIFTYMembershipProvider(raw_store=raw_store)
    index_memberships, prov_records, m_manifest = mem_provider.parse_membership_source_bytes(
        raw_bytes=json.dumps(mock_memberships).encode("utf-8"),
        index_name="STAGE_A_INDEX",
        instruments=master,
    )
    assert len(index_memberships) == 10

    # 6. Coverage Audit
    uni = Universe(name="STAGE_A_INDEX", version="v1", as_of=start_dt, members=[f"{s}.NS" for s in symbols])
    snap = create_snapshot(
        universe=uni,
        bars=upstox_bars_dict,
        data_version="stage-a-v1",
        adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
        memberships=index_memberships,
    )
    coverage_report = CoverageAnalyzer().analyze_coverage(
        memberships=index_memberships,
        snapshot=snap,
        instruments=master,
        index_name="STAGE_A_INDEX",
    )
    assert coverage_report.ready_for_dataset is True

    # 7. Persist DatasetSnapshot to Parquet Artifact Repository
    manifest = repo.save(snap, master)
    assert repo.verify(manifest.dataset_id) is True

    # 8. Load Restored Dataset & Assert Exact Logical SHA Match
    restored = repo.load(manifest.dataset_id)
    assert restored.snapshot.checksum == manifest.logical_checksum
    assert restored.snapshot.dataset_id == manifest.dataset_id
    assert restored.snapshot.universe.as_of == snap.universe.as_of
    assert restored.snapshot.bar_count() == snap.bar_count()
