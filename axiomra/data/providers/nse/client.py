"""NSE Network Client for fetching CM-UDiFF Bhavcopy ZIP files and Corporate Actions."""

from __future__ import annotations

import io
import urllib.request
import zipfile

from axiomra.storage.raw import RawFetchManifest, RawStore


class NSEClient:
    """Network fetcher for downloading raw EOD Bhavcopy ZIP and Corporate Action files from NSE India."""

    BHAVCOPY_ZIP_URL_FMT = "https://niftyindices.com/reports/BhavCopy_NSE_CM_0_0_0_{trade_date}_F_0000.csv.zip"
    CORPORATE_ACTIONS_URL = "https://www.nseindia.com/api/corporates-corporateactions?index=equities&csv=true"

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()

    def fetch_bhavcopy_bytes(
        self,
        trade_date: str,
        mock_bytes: bytes | None = None,
    ) -> tuple[bytes, RawFetchManifest]:
        """Fetch official NSE CM-UDiFF Bhavcopy ZIP, save raw bytes & manifest, extract & return unparsed CSV bytes."""
        if mock_bytes is not None:
            raw_bytes = mock_bytes
        else:
            url = self.BHAVCOPY_ZIP_URL_FMT.format(trade_date=trade_date)
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Accept": "application/zip, application/octet-stream, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_bytes = response.read()

        filename = f"bhavcopy_{trade_date}.zip" if raw_bytes.startswith(b"PK") else f"bhavcopy_{trade_date}.csv"
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="bhavcopy",
            filename=filename,
            data=raw_bytes,
            request_parameters={"trade_date": trade_date},
        )

        # Extract CSV if raw payload is a ZIP file
        if raw_bytes.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                csv_filename = [name for name in zf.namelist() if name.endswith(".csv")][0]
                extracted_csv_bytes = zf.read(csv_filename)
                return extracted_csv_bytes, manifest

        return raw_bytes, manifest

    def fetch_corporate_actions_bytes(
        self,
        mock_bytes: bytes | None = None,
    ) -> tuple[bytes, RawFetchManifest]:
        """Fetch unparsed NSE Corporate Action CSV bytes, validate headers, and store in RawStore with manifest."""
        if mock_bytes is not None:
            raw_bytes = mock_bytes
        else:
            req = urllib.request.Request(
                self.CORPORATE_ACTIONS_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Accept": "text/csv, application/csv, text/plain, */*",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_bytes = response.read()

        # Validate CSV content representation
        content_header = raw_bytes[:1024].decode("utf-8", errors="replace").upper()
        required_headers = ["SYMBOL", "PURPOSE", "EX-DATE"]
        missing_headers = [h for h in required_headers if h not in content_header and h.replace("-", "") not in content_header]
        if missing_headers:
            raise ValueError(f"Invalid NSE Corporate Action CSV response: missing required headers {missing_headers}")

        filename = "corporate_actions_nse.csv"
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="corporate_actions",
            filename=filename,
            data=raw_bytes,
        )
        return raw_bytes, manifest
