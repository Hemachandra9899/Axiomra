"""Historical Instrument Coverage & Delisted Constituent Audit Engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from axiomra.data.instruments import InstrumentMaster
from axiomra.data.snapshot import DatasetSnapshot
from axiomra.data.universe import IndexMembership


class ConstituentCoverageItem(BaseModel):
    """Coverage audit entry for a single index constituent."""

    instrument_id: str
    symbol: str
    index_name: str
    membership_from: datetime
    membership_until: datetime | None = None
    is_currently_active: bool = True
    is_delisted_or_removed: bool = False
    has_master_record: bool = False
    has_ohlcv_bars: bool = False
    bar_count: int = 0
    expected_sessions: int = 0
    actual_sessions: int = 0
    missing_sessions: int = 0
    coverage_ratio: float = 0.0
    first_required_date: datetime | None = None
    last_required_date: datetime | None = None
    first_actual_bar: datetime | None = None
    last_actual_bar: datetime | None = None
    has_corporate_actions: bool = False
    action_count: int = 0
    status: str = "PASS"
    """Status: 'PASS', 'DELISTED_INCLUDED', 'UNRESOLVED_ID', 'MISSING_BARS', 'DATA_GAP'."""
    notes: list[str] = Field(default_factory=list)


class HistoricalInstrumentCoverageReport(BaseModel):
    """Full coverage report over an index timeline, including delisted/removed constituent accounting."""

    index_name: str
    start_date: datetime
    end_date: datetime
    total_constituents: int = 0
    active_constituents: int = 0
    delisted_or_removed_constituents: int = 0
    resolved_id_count: int = 0
    unresolved_id_count: int = 0
    full_coverage_count: int = 0
    incomplete_coverage_count: int = 0
    items: list[ConstituentCoverageItem] = Field(default_factory=list)

    @property
    def ready_for_dataset(self) -> bool:
        """True if all historical constituents are resolved with complete OHLCV coverage."""
        return self.unresolved_id_count == 0 and self.incomplete_coverage_count == 0


class CoverageAnalyzer:
    """Audits dataset snapshots and membership records for full historical constituent coverage."""

    def __init__(self, min_coverage_ratio: float = 0.98) -> None:
        self.min_coverage_ratio = min_coverage_ratio

    def analyze_coverage(
        self,
        memberships: list[IndexMembership],
        snapshot: DatasetSnapshot,
        instruments: InstrumentMaster,
        index_name: str = "NIFTY 200",
    ) -> HistoricalInstrumentCoverageReport:
        """Analyze PIT index constituents using instrument_id-first bar resolution and 98% session coverage gating."""
        items: list[ConstituentCoverageItem] = []
        now_utc = datetime.now(UTC)

        all_timestamps = [
            b.timestamp for bars in snapshot.bars.values() for b in bars
        ]
        start_date = min(all_timestamps) if all_timestamps else now_utc
        end_date = max(all_timestamps) if all_timestamps else now_utc

        target_memberships = [m for m in memberships if m.index_name.upper() == index_name.upper()]

        total = len(target_memberships)
        active_cnt = 0
        delisted_cnt = 0
        resolved_cnt = 0
        unresolved_cnt = 0
        full_cnt = 0
        incomplete_cnt = 0

        # Build instrument_id -> list[Bar] lookup by resolving snapshot bar symbols
        id_to_bars: dict[str, list[Any]] = {}
        for sym, bars in snapshot.bars.items():
            for b in bars:
                resolved_inst = instruments.resolve_symbol(sym, b.timestamp)
                target_id = resolved_inst.instrument_id if resolved_inst is not None else sym
                id_to_bars.setdefault(target_id, []).append(b)

        for m in target_memberships:
            is_active = m.until_date is None or m.until_date > now_utc
            if is_active:
                active_cnt += 1
            else:
                delisted_cnt += 1

            inst = instruments.get(m.instrument_id) or instruments.resolve_symbol(m.symbol, m.from_date)
            has_master = inst is not None
            if has_master:
                resolved_cnt += 1
            else:
                unresolved_cnt += 1

            # Required interval bounds
            req_start = max(m.from_date, start_date)
            req_end = min(m.until_date, end_date) if m.until_date else end_date

            # Calculate expected weekday trading sessions
            expected_sessions = 0
            curr = req_start
            while curr <= req_end:
                if curr.weekday() < 5:
                    expected_sessions += 1
                curr += timedelta(days=1)

            # instrument_id-first bar lookup across all historical aliases
            all_inst_bars = sorted(id_to_bars.get(m.instrument_id, []), key=lambda b: b.timestamp)
            interval_bars = [
                b for b in all_inst_bars if req_start <= b.timestamp <= req_end
            ]

            actual_sessions = len({b.timestamp.date() for b in interval_bars})
            missing_sessions = max(0, expected_sessions - actual_sessions)
            coverage_ratio = actual_sessions / expected_sessions if expected_sessions > 0 else 1.0

            has_bars = len(all_inst_bars) > 0
            first_b = all_inst_bars[0].timestamp if all_inst_bars else None
            last_b = all_inst_bars[-1].timestamp if all_inst_bars else None

            # Check corporate action coverage
            actions = [a for a in snapshot.actions if a.instrument_id == m.instrument_id]

            notes: list[str] = []
            status = "PASS"

            if not has_master:
                status = "UNRESOLVED_ID"
                notes.append("Instrument identity not found in InstrumentMaster")
            elif not has_bars:
                status = "MISSING_BARS"
                notes.append("No OHLCV bars found in dataset snapshot")
            elif coverage_ratio < self.min_coverage_ratio:
                status = "DATA_GAP"
                notes.append(f"Coverage ratio {coverage_ratio:.3f} < threshold {self.min_coverage_ratio}")
            elif not is_active:
                status = "DELISTED_INCLUDED"
                notes.append("Historical constituent removed/delisted from index")

            if status in {"PASS", "DELISTED_INCLUDED"}:
                full_cnt += 1
            else:
                incomplete_cnt += 1

            item = ConstituentCoverageItem(
                instrument_id=m.instrument_id,
                symbol=m.symbol,
                index_name=m.index_name,
                membership_from=m.from_date,
                membership_until=m.until_date,
                is_currently_active=is_active,
                is_delisted_or_removed=not is_active,
                has_master_record=has_master,
                has_ohlcv_bars=has_bars,
                bar_count=len(all_inst_bars),
                expected_sessions=expected_sessions,
                actual_sessions=actual_sessions,
                missing_sessions=missing_sessions,
                coverage_ratio=coverage_ratio,
                first_required_date=req_start,
                last_required_date=req_end,
                first_actual_bar=first_b,
                last_actual_bar=last_b,
                has_corporate_actions=len(actions) > 0,
                action_count=len(actions),
                status=status,
                notes=notes,
            )
            items.append(item)

        return HistoricalInstrumentCoverageReport(
            index_name=index_name,
            start_date=start_date,
            end_date=end_date,
            total_constituents=total,
            active_constituents=active_cnt,
            delisted_or_removed_constituents=delisted_cnt,
            resolved_id_count=resolved_cnt,
            unresolved_id_count=unresolved_cnt,
            full_coverage_count=full_cnt,
            incomplete_coverage_count=incomplete_cnt,
            items=items,
        )
