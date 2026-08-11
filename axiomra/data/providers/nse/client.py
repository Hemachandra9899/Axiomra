"""NSE Network Client for fetching CM-UDiFF Bhavcopy and Corporate Actions."""

from __future__ import annotations

import urllib.request

from axiomra.storage.raw import RawFetchManifest, RawStore


class NSEClient:
    """Network fetcher for downloading raw EOD Bhavcopy and Corporate Action files from NSE India."""

    BHAVCOPY_URL_FMT = "https://niftyindices.com/reports/CMUDiFF_bhavcopy_{trade_date}.csv"
    CORPORATE_ACTIONS_URL = "https://www.nseindia.com/api/corporates-corporateactions"

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()

    def fetch_bhavcopy_bytes(
        self,
        trade_date: str,
        mock_bytes: bytes | None = None,
    ) -> tuple[bytes, RawFetchManifest]:
        """Fetch unparsed NSE Bhavcopy CSV bytes and store in RawStore with manifest."""
        if mock_bytes is not None:
            raw_bytes = mock_bytes
        else:
            url = self.BHAVCOPY_URL_FMT.format(trade_date=trade_date)
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_bytes = response.read()

        filename = f"bhavcopy_{trade_date}.csv"
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="bhavcopy",
            filename=filename,
            data=raw_bytes,
            request_parameters={"trade_date": trade_date},
        )
        return raw_bytes, manifest

    def fetch_corporate_actions_bytes(
        self,
        mock_bytes: bytes | None = None,
    ) -> tuple[bytes, RawFetchManifest]:
        """Fetch unparsed NSE Corporate Action CSV/JSON bytes and store in RawStore with manifest."""
        if mock_bytes is not None:
            raw_bytes = mock_bytes
        else:
            req = urllib.request.Request(
                self.CORPORATE_ACTIONS_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Accept": "application/json, text/csv",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_bytes = response.read()

        filename = "corporate_actions_nse.csv"
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="corporate_actions",
            filename=filename,
            data=raw_bytes,
        )
        return raw_bytes, manifest
