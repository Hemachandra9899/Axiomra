"""Historical Instrument Coverage & Delisted Constituent Audit Engine."""

from __future__ import annotations

from datetime import UTC, datetime

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
    first_bar_date: datetime | None = None
    last_bar_date: datetime | None = None
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

    def analyze_coverage(
        self,
        memberships: list[IndexMembership],
        snapshot: DatasetSnapshot,
        instruments: InstrumentMaster,
        index_name: str = "NIFTY 200",
    ) -> HistoricalInstrumentCoverageReport:
        """Analyze PIT index constituents, mapping resolution, bar coverage, and delisting status."""
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

        for m in target_memberships:
            is_active = m.until_date is None or m.until_date > now_utc
            if is_active:
                active_cnt += 1
            else:
                delisted_cnt += 1

            inst = instruments.resolve_symbol(m.symbol, m.from_date)
            has_master = inst is not None
            if has_master:
                resolved_cnt += 1
            else:
                unresolved_cnt += 1

            # Check bar coverage in snapshot
            symbol_bars = snapshot.bars.get(m.symbol, [])
            has_bars = len(symbol_bars) > 0
            bar_cnt = len(symbol_bars)
            first_b = symbol_bars[0].timestamp if symbol_bars else None
            last_b = symbol_bars[-1].timestamp if symbol_bars else None

            # Check action coverage
            actions = [a for a in snapshot.actions if a.instrument_id == m.instrument_id]
            has_actions = len(actions) > 0

            notes: list[str] = []
            status = "PASS"

            if not has_master:
                status = "UNRESOLVED_ID"
                notes.append("Instrument identity not found in InstrumentMaster")
            elif not has_bars:
                status = "MISSING_BARS"
                notes.append("No OHLCV bars found in dataset snapshot")
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
                bar_count=bar_cnt,
                first_bar_date=first_b,
                last_bar_date=last_b,
                has_corporate_actions=has_actions,
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
