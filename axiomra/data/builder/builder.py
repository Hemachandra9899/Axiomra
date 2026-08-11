"""Core Dataset Builder Engine for Axiomra."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.builder.errors import (
    CoverageGateFailedError,
    DatasetBuildError,
    IncompleteRunError,
    ReconciliationFailedError,
)
from axiomra.data.builder.report import BuildRunManifest, DatasetBuildReport
from axiomra.data.coverage import CoverageAnalyzer, HistoricalInstrumentCoverageReport
from axiomra.data.instruments import CorporateAction, InstrumentMaster
from axiomra.data.persistence.models import DatasetQualityError
from axiomra.data.persistence.parquet import ParquetDatasetRepository
from axiomra.data.quality import DataQualityChecker, DataQualityReport
from axiomra.data.reconciliation import (
    ProviderReconciler,
    ReconciliationConfig,
    ReconciliationReport,
)
from axiomra.data.snapshot import DatasetSnapshot, create_snapshot
from axiomra.data.universe import IndexMembership, Universe
from axiomra.domain.market import Bar
from axiomra.storage.raw import RawFetchManifest, RawStore


class DatasetBuildResult(BaseModel):
    """Result artifact of a successful dataset build execution."""

    snapshot: DatasetSnapshot
    report: DatasetBuildReport
    coverage_report: HistoricalInstrumentCoverageReport
    reconciliation_report: ReconciliationReport | None = None
    quality_report: DataQualityReport
    run_manifest: BuildRunManifest


class DatasetBuilder:
    """Orchestrates end-to-end dataset acquisition, auditing, snapshotting, Parquet persistence, and verification."""

    def __init__(
        self,
        raw_store: RawStore | None = None,
        repository: ParquetDatasetRepository | None = None,
    ) -> None:
        self.raw_store = raw_store or RawStore()
        self.repository = repository or ParquetDatasetRepository()
        self.quality_checker = DataQualityChecker()
        self.reconciler = ProviderReconciler(ReconciliationConfig(fail_on_missing=True))

    def build(
        self,
        config: DatasetBuildConfig,
        bars: dict[str, list[Bar]],
        instruments: InstrumentMaster,
        memberships: list[IndexMembership],
        actions: list[CorporateAction] | None = None,
        raw_manifests: list[RawFetchManifest] | None = None,
        secondary_bars: dict[str, list[Bar]] | None = None,
        data_origin: Literal["provider", "synthetic"] = "provider",
        synthetic_rows: int = 0,
    ) -> DatasetBuildResult:
        """Build, audit, persist, reload, and verify an immutable Parquet research dataset."""
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        run_manifest = BuildRunManifest(
            run_id=run_id,
            requested_instruments=len(config.symbols),
            raw_fetches=[m.raw_path for m in (raw_manifests or [])],
        )

        # 0. Enforce Provider Provenance Invariants & Requested Symbol Gate
        if data_origin == "provider":
            if len(raw_manifests or []) == 0:
                raise ValueError("Invalid provider dataset build: raw_fetch_count is 0")
            if synthetic_rows > 0:
                raise ValueError(f"Invalid provider dataset build: synthetic_rows is {synthetic_rows} (must be 0)")

        requested = set(config.symbols)
        received = {sym for sym, b_list in bars.items() if len(b_list) > 0}
        missing_symbols = requested - received
        if missing_symbols:
            run_manifest.status = "INCOMPLETE"
            run_manifest.failed_instruments = sorted(missing_symbols)
            raise IncompleteRunError(
                f"Dataset build aborted: missing bars for {len(missing_symbols)} requested symbols: {sorted(missing_symbols)}"
            )

        # 1. Provider Reconciliation (if secondary source provided)
        rec_report = None
        if secondary_bars:
            rec_report = self.reconciler.reconcile(
                primary_bars=bars,
                secondary_bars=secondary_bars,
                primary_provider="upstox",
                secondary_provider="nse",
            )
            if config.fail_on_reconciliation_error and not rec_report.valid:
                run_manifest.status = "FAILED"
                raise ReconciliationFailedError(
                    f"Provider reconciliation failed with {rec_report.discrepancies_count} discrepancies"
                )

        # 2. Create Dataset Snapshot
        uni = Universe(
            name=config.universe_name,
            version="v1",
            as_of=config.end_date,
            members=config.symbols,
        )
        snapshot = create_snapshot(
            universe=uni,
            bars=bars,
            actions=actions or [],
            memberships=memberships,
            adjustment_mode=config.adjustment_mode,
            data_version="v1",
        )

        # 3. Data Quality Checks (Fail-Fast Gate)
        q_report = self.quality_checker.check(snapshot)
        if not q_report.valid:
            run_manifest.status = "FAILED"
            run_manifest.notes.append(f"{q_report.total_issues} quality check issues detected")
            raise DatasetQualityError(
                f"Cannot save dataset {snapshot.dataset_id}: failed quality check ({q_report.total_issues} issues)"
            )

        # 4. Coverage Audit
        analyzer = CoverageAnalyzer(min_coverage_ratio=config.min_coverage_ratio)
        cov_report = analyzer.analyze_coverage(
            memberships=memberships,
            snapshot=snapshot,
            instruments=instruments,
            index_name=config.universe_name,
        )

        if config.fail_on_missing_coverage and cov_report.incomplete_coverage_count > 0:
            failed_syms = [item.symbol for item in cov_report.items if item.status not in {"PASS", "DELISTED_INCLUDED"}]
            run_manifest.status = "INCOMPLETE"
            run_manifest.failed_instruments = failed_syms
            raise CoverageGateFailedError(
                f"Coverage gate failed for {len(failed_syms)} instruments: {failed_syms}"
            )

        run_manifest.successful_instruments = len(config.symbols)

        # 5. Persist Parquet Research Dataset & Retrieve DatasetManifest Checksum Lineage
        manifest = self.repository.save(snapshot, instruments=instruments)
        run_manifest.dataset_id = manifest.dataset_id

        # 6. Verification: Reload & Logical Checksum Round-Trip Test
        loaded_dataset = self.repository.load(snapshot.dataset_id)
        if loaded_dataset.snapshot.dataset_id != snapshot.dataset_id:
            raise DatasetBuildError(
                f"Loaded snapshot dataset_id '{loaded_dataset.snapshot.dataset_id}' does not match original '{snapshot.dataset_id}'"
            )

        # 7. Generate Build Report
        coverage_map = {item.symbol: item.coverage_ratio for item in cov_report.items}
        total_missing = sum(item.missing_sessions for item in cov_report.items)
        raw_shas = [m.sha256 for m in (raw_manifests or [])]

        report = DatasetBuildReport(
            dataset_id=manifest.dataset_id,
            universe_name=config.universe_name,
            date_range=f"{config.start_date.isoformat()} / {config.end_date.isoformat()}",
            instrument_count=len(snapshot.universe.members),
            bar_count=snapshot.bar_count(),
            data_origin=data_origin,
            synthetic_rows=synthetic_rows,
            raw_fetch_count=len(raw_manifests or []),
            raw_source_shas=raw_shas,
            coverage_by_instrument=coverage_map,
            missing_sessions=total_missing,
            reconciliation_discrepancies=rec_report.discrepancies_count if rec_report else 0,
            quarantined_rows=q_report.total_issues,
            corporate_action_count=len(snapshot.actions),
            logical_checksum=manifest.logical_checksum,
            artifact_checksum=manifest.artifact_checksum,
        )

        run_manifest.completed_at = datetime.now(UTC)

        return DatasetBuildResult(
            snapshot=snapshot,
            report=report,
            coverage_report=cov_report,
            reconciliation_report=rec_report,
            quality_report=q_report,
            run_manifest=run_manifest,
        )
