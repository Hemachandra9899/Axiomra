"""Parquet implementation of DatasetRepository."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pandas as pd

from axiomra.data.instruments import (
    CorporateAction,
    Instrument,
    InstrumentMaster,
)
from axiomra.data.persistence.models import DatasetQualityError, PersistedDataset
from axiomra.data.persistence.repository import DatasetRepository
from axiomra.data.quality import DataQualityChecker
from axiomra.data.snapshot import DatasetSnapshot, create_snapshot
from axiomra.data.universe import IndexMembership, Universe
from axiomra.domain.market import Bar
from axiomra.storage.base import ArtifactStore
from axiomra.storage.hashing import sha256_bytes
from axiomra.storage.local import LocalArtifactStore
from axiomra.storage.manifest import (
    SUPPORTED_DATASET_SCHEMAS,
    DatasetManifest,
    FileArtifact,
    UnsupportedSchemaError,
)


class ParquetDatasetRepository(DatasetRepository):
    """Dataset persistence using Parquet tables and checksummed manifests."""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or LocalArtifactStore()

    def _dataset_dir(self, dataset_id: str) -> str:
        return f"datasets/{dataset_id}"

    def save(
        self,
        snapshot: DatasetSnapshot,
        instruments: InstrumentMaster,
        allow_invalid: bool = False,
    ) -> DatasetManifest:
        # Quality Gate
        checker = DataQualityChecker()
        quality_report = checker.check(snapshot)
        if not quality_report.valid and not allow_invalid:
            raise DatasetQualityError(
                f"Cannot save dataset {snapshot.dataset_id}: failed quality check ({quality_report.total_issues} issues)"
            )

        dataset_id = snapshot.dataset_id
        prefix = self._dataset_dir(dataset_id)

        file_artifacts: dict[str, FileArtifact] = {}

        # 1. bars.parquet
        bar_rows: list[dict] = []
        for symbol, bars in snapshot.bars.items():
            for b in bars:
                resolved = instruments.resolve_symbol(symbol, b.timestamp)
                inst_id = resolved.instrument_id if resolved is not None else symbol
                bar_rows.append(
                    {
                        "instrument_id": inst_id,
                        "symbol": b.symbol,
                        "timestamp": b.timestamp.isoformat(),
                        "open": float(b.open),
                        "high": float(b.high),
                        "low": float(b.low),
                        "close": float(b.close),
                        "volume": float(b.volume),
                    }
                )

        if bar_rows:
            df_bars = pd.DataFrame(bar_rows)
            df_bars = df_bars.sort_values(["instrument_id", "timestamp"]).reset_index(drop=True)
        else:
            df_bars = pd.DataFrame(
                columns=["instrument_id", "symbol", "timestamp", "open", "high", "low", "close", "volume"]
            )

        buf_bars = io.BytesIO()
        df_bars.to_parquet(buf_bars, index=False)
        bytes_bars = buf_bars.getvalue()
        key_bars = f"{prefix}/bars.parquet"
        self.store.put_bytes(key_bars, bytes_bars)
        file_artifacts["bars.parquet"] = FileArtifact(
            path=key_bars,
            sha256=sha256_bytes(bytes_bars),
            rows=len(df_bars),
        )

        # 2. instruments.parquet
        inst_rows: list[dict] = []
        for inst in instruments._all_instruments:
            inst_rows.append(
                {
                    "instrument_id": inst.instrument_id,
                    "symbol": inst.symbol,
                    "exchange": inst.exchange,
                    "isin": inst.isin,
                    "name": inst.name,
                    "sector": inst.sector,
                    "industry": inst.industry,
                    "active_from": inst.active_from.isoformat(),
                    "active_until": inst.active_until.isoformat() if inst.active_until else None,
                }
            )
        df_inst = pd.DataFrame(inst_rows) if inst_rows else pd.DataFrame(
            columns=["instrument_id", "symbol", "exchange", "isin", "name", "sector", "industry", "active_from", "active_until"]
        )
        buf_inst = io.BytesIO()
        df_inst.to_parquet(buf_inst, index=False)
        bytes_inst = buf_inst.getvalue()
        key_inst = f"{prefix}/instruments.parquet"
        self.store.put_bytes(key_inst, bytes_inst)
        file_artifacts["instruments.parquet"] = FileArtifact(
            path=key_inst,
            sha256=sha256_bytes(bytes_inst),
            rows=len(df_inst),
        )

        # 3. memberships.parquet
        mem_rows: list[dict] = []
        for m in snapshot.memberships:
            mem_rows.append(
                {
                    "index_name": m.index_name,
                    "instrument_id": m.instrument_id,
                    "symbol": m.symbol,
                    "valid_from": m.from_date.isoformat(),
                    "valid_until": m.until_date.isoformat() if m.until_date else None,
                }
            )
        df_mem = pd.DataFrame(mem_rows) if mem_rows else pd.DataFrame(
            columns=["index_name", "instrument_id", "symbol", "valid_from", "valid_until"]
        )
        buf_mem = io.BytesIO()
        df_mem.to_parquet(buf_mem, index=False)
        bytes_mem = buf_mem.getvalue()
        key_mem = f"{prefix}/memberships.parquet"
        self.store.put_bytes(key_mem, bytes_mem)
        file_artifacts["memberships.parquet"] = FileArtifact(
            path=key_mem,
            sha256=sha256_bytes(bytes_mem),
            rows=len(df_mem),
        )

        # 4. corporate_actions.parquet
        action_rows: list[dict] = []
        for a in snapshot.actions:
            action_type_str = a.action_type.value if hasattr(a.action_type, "value") else str(a.action_type)
            action_rows.append(
                {
                    "instrument_id": a.instrument_id,
                    "action_type": action_type_str,
                    "ex_date": a.ex_date.isoformat(),
                    "ratio": a.ratio,
                    "amount": a.amount,
                    "currency": a.currency,
                    "note": a.note,
                }
            )
        df_act = pd.DataFrame(action_rows) if action_rows else pd.DataFrame(
            columns=["instrument_id", "action_type", "ex_date", "ratio", "amount", "currency", "note"]
        )
        buf_act = io.BytesIO()
        df_act.to_parquet(buf_act, index=False)
        bytes_act = buf_act.getvalue()
        key_act = f"{prefix}/corporate_actions.parquet"
        self.store.put_bytes(key_act, bytes_act)
        file_artifacts["corporate_actions.parquet"] = FileArtifact(
            path=key_act,
            sha256=sha256_bytes(bytes_act),
            rows=len(df_act),
        )

        # 5. quality_report.json
        bytes_qr = quality_report.model_dump_json(indent=2).encode("utf-8")
        key_qr = f"{prefix}/quality_report.json"
        self.store.put_bytes(key_qr, bytes_qr)
        file_artifacts["quality_report.json"] = FileArtifact(
            path=key_qr,
            sha256=sha256_bytes(bytes_qr),
            rows=len(quality_report.checks),
        )

        # Dates boundary calculation
        all_timestamps = [
            b.timestamp for bars in snapshot.bars.values() for b in bars
        ]
        start_date = min(all_timestamps).date() if all_timestamps else snapshot.universe.as_of.date()
        end_date = max(all_timestamps).date() if all_timestamps else snapshot.universe.as_of.date()

        # Compute artifact_checksum over canonical JSON of files dict
        manifest_payload = {
            "schema_version": "dataset-v1",
            "dataset_id": dataset_id,
            "logical_checksum": snapshot.checksum,
            "files": {
                name: artifact.model_dump()
                for name, artifact in sorted(file_artifacts.items())
            },
        }
        canonical_manifest_str = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":"))
        artifact_checksum = sha256_bytes(canonical_manifest_str.encode("utf-8"))

        manifest = DatasetManifest(
            schema_version="dataset-v1",
            dataset_id=dataset_id,
            logical_checksum=snapshot.checksum,
            artifact_checksum=artifact_checksum,
            created_at=datetime.now(UTC),
            data_version=snapshot.data_version,
            adjustment_mode=snapshot.adjustment_mode,
            universe_name=snapshot.universe.name,
            universe_version=snapshot.universe.version,
            universe_as_of=snapshot.universe.as_of,
            universe_members=list(snapshot.universe.members),
            start_date=start_date,
            end_date=end_date,
            instrument_count=snapshot.symbol_count(),
            bar_count=snapshot.bar_count(),
            files=file_artifacts,
        )

        bytes_manifest = manifest.model_dump_json(indent=2).encode("utf-8")
        key_manifest = f"{prefix}/manifest.json"
        self.store.put_bytes(key_manifest, bytes_manifest)

        return manifest

    def load(self, dataset_id: str) -> PersistedDataset:
        prefix = self._dataset_dir(dataset_id)
        key_manifest = f"{prefix}/manifest.json"
        if not self.store.exists(key_manifest):
            raise FileNotFoundError(f"Dataset manifest not found: {key_manifest}")

        manifest_data = json.loads(self.store.get_bytes(key_manifest).decode("utf-8"))
        manifest = DatasetManifest.model_validate(manifest_data)

        if manifest.schema_version not in SUPPORTED_DATASET_SCHEMAS:
            raise UnsupportedSchemaError(
                f"Unsupported dataset schema version: {manifest.schema_version!r}"
            )

        # 1. Restore InstrumentMaster & CorporateActions
        master = InstrumentMaster()
        bytes_inst = self.store.get_bytes(f"{prefix}/instruments.parquet")
        df_inst = pd.read_parquet(io.BytesIO(bytes_inst))

        for _, row in df_inst.iterrows():
            master.upsert(
                Instrument(
                    instrument_id=str(row["instrument_id"]),
                    symbol=str(row["symbol"]),
                    exchange=str(row["exchange"]),
                    isin=str(row["isin"]) if pd.notna(row["isin"]) else None,
                    name=str(row["name"]) if pd.notna(row["name"]) else None,
                    sector=str(row["sector"]) if pd.notna(row["sector"]) else None,
                    industry=str(row["industry"]) if pd.notna(row["industry"]) else None,
                    active_from=datetime.fromisoformat(str(row["active_from"])),
                    active_until=datetime.fromisoformat(str(row["active_until"])) if pd.notna(row["active_until"]) and row["active_until"] is not None else None,
                )
            )

        bytes_act = self.store.get_bytes(f"{prefix}/corporate_actions.parquet")
        df_act = pd.read_parquet(io.BytesIO(bytes_act))
        actions: list[CorporateAction] = []

        for _, row in df_act.iterrows():
            act = CorporateAction(
                instrument_id=str(row["instrument_id"]),
                action_type=str(row["action_type"]),
                ex_date=datetime.fromisoformat(str(row["ex_date"])),
                ratio=float(row["ratio"]) if pd.notna(row["ratio"]) else None,
                amount=float(row["amount"]) if pd.notna(row["amount"]) else None,
                currency=str(row["currency"]) if pd.notna(row["currency"]) else "INR",
                note=str(row["note"]) if pd.notna(row["note"]) else None,
            )
            actions.append(act)
            master.add_action(act)

        # 2. Restore Memberships
        bytes_mem = self.store.get_bytes(f"{prefix}/memberships.parquet")
        df_mem = pd.read_parquet(io.BytesIO(bytes_mem))
        memberships: list[IndexMembership] = []

        for _, row in df_mem.iterrows():
            memberships.append(
                IndexMembership(
                    index_name=str(row["index_name"]),
                    instrument_id=str(row["instrument_id"]),
                    symbol=str(row["symbol"]),
                    from_date=datetime.fromisoformat(str(row["valid_from"])),
                    until_date=datetime.fromisoformat(str(row["valid_until"])) if pd.notna(row["valid_until"]) and row["valid_until"] is not None else None,
                )
            )

        # 3. Restore Bars
        bytes_bars = self.store.get_bytes(f"{prefix}/bars.parquet")
        df_bars = pd.read_parquet(io.BytesIO(bytes_bars))
        bars_by_symbol: dict[str, list[Bar]] = {}

        for symbol, group in df_bars.groupby("symbol"):
            bar_list = []
            for _, row in group.iterrows():
                bar_list.append(
                    Bar(
                        symbol=str(row["symbol"]),
                        timestamp=datetime.fromisoformat(str(row["timestamp"])),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
            bars_by_symbol[str(symbol)] = bar_list

        # Universe — restore from manifest to preserve exact logical identity
        universe = Universe(
            name=manifest.universe_name,
            version=manifest.universe_version,
            as_of=manifest.universe_as_of,
            members=manifest.universe_members if manifest.universe_members else list(bars_by_symbol.keys()),
        )

        snapshot = create_snapshot(
            universe=universe,
            bars=bars_by_symbol,
            data_version=manifest.data_version,
            actions=actions,
            adjustment_mode=manifest.adjustment_mode,
            memberships=memberships,
        )

        return PersistedDataset(
            snapshot=snapshot,
            manifest=manifest,
            instrument_master=master,
        )

    def verify(self, dataset_id: str) -> bool:
        prefix = self._dataset_dir(dataset_id)
        key_manifest = f"{prefix}/manifest.json"
        if not self.store.exists(key_manifest):
            return False

        try:
            manifest_data = json.loads(self.store.get_bytes(key_manifest).decode("utf-8"))
            manifest = DatasetManifest.model_validate(manifest_data)
        except Exception:
            return False

        # Verify each file hash
        for filename, file_art in manifest.files.items():
            if not self.store.exists(file_art.path):
                return False
            try:
                actual_bytes = self.store.get_bytes(file_art.path)
                actual_hash = sha256_bytes(actual_bytes)
                if actual_hash != file_art.sha256:
                    return False
            except Exception:
                return False

        # Re-compute artifact_checksum
        manifest_payload = {
            "schema_version": "dataset-v1",
            "dataset_id": dataset_id,
            "logical_checksum": manifest.logical_checksum,
            "files": {
                name: artifact.model_dump()
                for name, artifact in sorted(manifest.files.items())
            },
        }
        canonical_manifest_str = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":"))
        expected_artifact_checksum = sha256_bytes(canonical_manifest_str.encode("utf-8"))

        return manifest.artifact_checksum == expected_artifact_checksum
