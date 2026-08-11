"""Data Provider Reconciliation Engine and Quarantine Suite.

Cross-checks sampled OHLCV bars across multiple providers (e.g. Upstox vs NSE Bhavcopy),
calculates price/volume discrepancy metrics, and flags/quarantines suspect bars.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from axiomra.domain.market import Bar


class ReconciliationConfig(BaseModel):
    """Tolerance thresholds for provider discrepancy checks."""

    max_close_diff_bps: float = 10.0
    """Maximum allowed difference in close price in basis points (10 bps = 0.1%)."""

    max_volume_diff_pct: float = 5.0
    """Maximum allowed difference in volume in percentage points (5.0 = 5%)."""

    fail_on_missing: bool = True
    """Whether unexpected missing dates from a provider cause report.valid to evaluate to False."""


class ReconciliationItem(BaseModel):
    """Detailed reconciliation check result for a single symbol × date."""

    symbol: str
    date: date
    upstox_close: float | None = None
    nse_close: float | None = None
    close_diff_bps: float = 0.0
    upstox_volume: float | None = None
    nse_volume: float | None = None
    volume_diff_pct: float = 0.0
    status: str = "PASS"
    """Status: 'PASS', 'QUARANTINE', 'MISSING_UPSTOX', 'MISSING_NSE', 'DUPLICATE'."""
    note: str | None = None


class ReconciliationReport(BaseModel):
    """Aggregate provider reconciliation audit report."""

    config: ReconciliationConfig
    total_checked: int = 0
    passed_count: int = 0
    quarantined_count: int = 0
    items: list[ReconciliationItem] = Field(default_factory=list)
    quarantined_items: list[ReconciliationItem] = Field(default_factory=list)
    missing_dates: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        """True if zero quarantined bars AND (if fail_on_missing) zero missing provider dates."""
        has_no_quarantine = self.quarantined_count == 0
        has_no_missing = not self.config.fail_on_missing or len(self.missing_dates) == 0
        return has_no_quarantine and has_no_missing


class ProviderReconciler:
    """Reconciles OHLCV series between primary provider (Upstox) and secondary provider (NSE)."""

    def __init__(self, config: ReconciliationConfig | None = None) -> None:
        self.config = config or ReconciliationConfig()

    def reconcile_symbol_series(
        self,
        symbol: str,
        upstox_bars: list[Bar],
        nse_bars: list[Bar],
    ) -> ReconciliationReport:
        """Compare Upstox daily bars against NSE Bhavcopy daily bars for a given symbol."""
        u_by_date: dict[date, list[Bar]] = {}
        for b in upstox_bars:
            d = b.timestamp.date()
            u_by_date.setdefault(d, []).append(b)

        n_by_date: dict[date, list[Bar]] = {}
        for b in nse_bars:
            d = b.timestamp.date()
            n_by_date.setdefault(d, []).append(b)

        all_dates = sorted(set(u_by_date.keys()) | set(n_by_date.keys()))
        items: list[ReconciliationItem] = []
        quarantined: list[ReconciliationItem] = []
        missing: list[dict[str, Any]] = []

        for dt in all_dates:
            u_list = u_by_date.get(dt, [])
            n_list = n_by_date.get(dt, [])

            # Duplicate check
            if len(u_list) > 1 or len(n_list) > 1:
                item = ReconciliationItem(
                    symbol=symbol,
                    date=dt,
                    status="QUARANTINE",
                    note=f"Duplicate dates detected: upstox={len(u_list)}, nse={len(n_list)}",
                )
                items.append(item)
                quarantined.append(item)
                continue

            # Missing date check
            if not u_list:
                missing.append({"symbol": symbol, "date": dt.isoformat(), "missing_provider": "upstox"})
                items.append(ReconciliationItem(symbol=symbol, date=dt, status="MISSING_UPSTOX"))
                continue
            if not n_list:
                missing.append({"symbol": symbol, "date": dt.isoformat(), "missing_provider": "nse"})
                items.append(ReconciliationItem(symbol=symbol, date=dt, status="MISSING_NSE"))
                continue

            ub = u_list[0]
            nb = n_list[0]

            # Price diff in bps
            close_diff_bps = (abs(ub.close - nb.close) / nb.close * 10_000.0) if nb.close > 0 else 0.0

            # Volume diff in pct
            vol_base = max(nb.volume, 1.0)
            vol_diff_pct = (abs(ub.volume - nb.volume) / vol_base) * 100.0

            is_quarantine = (
                close_diff_bps > self.config.max_close_diff_bps
                or vol_diff_pct > self.config.max_volume_diff_pct
            )

            status = "QUARANTINE" if is_quarantine else "PASS"
            note = None
            if is_quarantine:
                reasons = []
                if close_diff_bps > self.config.max_close_diff_bps:
                    reasons.append(f"close diff {close_diff_bps:.1f} bps > {self.config.max_close_diff_bps} bps")
                if vol_diff_pct > self.config.max_volume_diff_pct:
                    reasons.append(f"vol diff {vol_diff_pct:.1f}% > {self.config.max_volume_diff_pct}%")
                note = "Quarantined due to: " + ", ".join(reasons)

            item = ReconciliationItem(
                symbol=symbol,
                date=dt,
                upstox_close=ub.close,
                nse_close=nb.close,
                close_diff_bps=close_diff_bps,
                upstox_volume=ub.volume,
                nse_volume=nb.volume,
                volume_diff_pct=vol_diff_pct,
                status=status,
                note=note,
            )
            items.append(item)
            if is_quarantine:
                quarantined.append(item)

        passed = [i for i in items if i.status == "PASS"]
        return ReconciliationReport(
            config=self.config,
            total_checked=len(items),
            passed_count=len(passed),
            quarantined_count=len(quarantined),
            items=items,
            quarantined_items=quarantined,
            missing_dates=missing,
        )
