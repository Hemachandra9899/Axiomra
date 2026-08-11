"""NSE Corporate Action CSV/JSON Provider and Parser."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime
from typing import Any

from axiomra.data.instruments import (
    CorporateAction,
    CorporateActionType,
    InstrumentMaster,
)
from axiomra.storage.raw import RawFetchManifest, RawStore


class NSECorporateActionProvider:
    """Parses NSE corporate action reports (CSV or JSON) into structured CorporateAction models."""

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()

    def parse_actions_bytes(
        self,
        raw_bytes: bytes,
        filename: str = "corporate_actions_nse.csv",
        instruments: InstrumentMaster | None = None,
        parser_version: str = "v1",
    ) -> tuple[list[CorporateAction], RawFetchManifest]:
        """Parse raw NSE Corporate Action CSV or JSON bytes into structured CorporateAction records."""
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="corporate_actions",
            filename=filename,
            data=raw_bytes,
            parser_version=parser_version,
        )

        content = raw_bytes.decode("utf-8", errors="replace").strip()
        actions: list[CorporateAction] = []

        if content.startswith("[") or content.startswith("{"):
            try:
                data_obj = json.loads(content)
                records: list[dict[str, Any]] = data_obj if isinstance(data_obj, list) else data_obj.get("data", [])
                for item in records:
                    raw_sym = str(item.get("symbol") or item.get("SYMBOL") or "").strip()
                    if not raw_sym:
                        continue
                    symbol_ns = raw_sym if raw_sym.endswith(".NS") else f"{raw_sym}.NS"
                    purpose = str(item.get("subject") or item.get("PURPOSE") or item.get("purpose") or "").strip()
                    ex_date_str = str(item.get("exDate") or item.get("EX-DATE") or item.get("ex_date") or "").strip()

                    if not ex_date_str or ex_date_str == "-":
                        continue

                    ex_date = self._parse_date(ex_date_str)
                    if ex_date is None:
                        continue

                    instrument_id = symbol_ns
                    if instruments is not None:
                        resolved = instruments.resolve_symbol(symbol_ns, ex_date)
                        if resolved is not None:
                            instrument_id = resolved.instrument_id

                    action_type, ratio, amount = self._classify_purpose(purpose)
                    actions.append(
                        CorporateAction(
                            instrument_id=instrument_id,
                            action_type=action_type,
                            ex_date=ex_date,
                            ratio=ratio,
                            amount=amount,
                            currency="INR",
                            note=purpose,
                            raw_description=purpose,
                            source="NSE",
                        )
                    )
                return actions, manifest
            except Exception:
                pass

        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            raw_sym = (row.get("SYMBOL") or row.get("Symbol") or "").strip()
            if not raw_sym:
                continue

            symbol_ns = raw_sym if raw_sym.endswith(".NS") else f"{raw_sym}.NS"
            purpose = (row.get("PURPOSE") or row.get("Purpose") or "").strip()
            ex_date_str = (row.get("EX-DATE") or row.get("Ex-Date") or row.get("Ex Date") or "").strip()

            if not ex_date_str:
                continue

            ex_date = self._parse_date(ex_date_str)
            if ex_date is None:
                continue

            instrument_id = symbol_ns
            if instruments is not None:
                resolved = instruments.resolve_symbol(symbol_ns, ex_date)
                if resolved is not None:
                    instrument_id = resolved.instrument_id

            action_type, ratio, amount = self._classify_purpose(purpose)

            action = CorporateAction(
                instrument_id=instrument_id,
                action_type=action_type,
                ex_date=ex_date,
                ratio=ratio,
                amount=amount,
                currency="INR",
                note=purpose,
                raw_description=purpose,
                source="NSE",
            )
            actions.append(action)

        return actions, manifest

    def _parse_date(self, date_str: str) -> datetime | None:
        formats = ["%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
            except ValueError:
                pass
        return None

    def _classify_purpose(self, purpose: str) -> tuple[CorporateActionType | str, float | None, float | None]:
        p_upper = purpose.upper()

        # Dividend extraction
        if "DIVIDEND" in p_upper:
            amt = None
            match = re.search(r"(?:RS\.?|INR)\s*([0-9]+(?:\.[0-9]+)?)", p_upper)
            if match:
                try:
                    amt = float(match.group(1))
                except ValueError:
                    pass
            return CorporateActionType.DIVIDEND, None, amt

        # Bonus extraction
        if "BONUS" in p_upper:
            ratio = None
            match = re.search(r"(\d+)\s*:\s*(\d+)", p_upper)
            if match:
                bonus_shares = float(match.group(1))
                held_shares = float(match.group(2))
                if held_shares > 0:
                    ratio = (held_shares + bonus_shares) / held_shares
            return CorporateActionType.BONUS, ratio, None

        # Split extraction
        if "SPLIT" in p_upper or "SUB-DIVISION" in p_upper or "SUB DIVISION" in p_upper:
            ratio = None
            match = re.search(r"FROM\s*(?:RS\.?|INR)?\s*(\d+)\s*TO\s*(?:RS\.?|INR)?\s*(\d+)", p_upper)
            if match:
                old_val = float(match.group(1))
                new_val = float(match.group(2))
                if new_val > 0:
                    ratio = old_val / new_val
            elif ":" in p_upper:
                match2 = re.search(r"(\d+)\s*:\s*(\d+)", p_upper)
                if match2:
                    n1 = float(match2.group(1))
                    n2 = float(match2.group(2))
                    if n2 > 0:
                        ratio = n1 / n2
            return CorporateActionType.SPLIT, ratio, None

        if "CONSOLIDATION" in p_upper:
            return CorporateActionType.CONSOLIDATION, None, None

        if "RIGHTS" in p_upper:
            return CorporateActionType.RIGHTS, None, None

        if "DEMERGER" in p_upper:
            return CorporateActionType.DEMERGER, None, None

        if "SYMBOL" in p_upper and "CHANGE" in p_upper:
            return CorporateActionType.SYMBOL_CHANGE, None, None

        return CorporateActionType.SYMBOL_CHANGE if "NAME" in p_upper else purpose, None, None
