"""NSE Network Client for fetching CM-UDiFF Bhavcopy ZIP files and Corporate Actions."""

from __future__ import annotations

import io
import json
import subprocess
import urllib.request
import zipfile

from axiomra.storage.raw import RawFetchManifest, RawStore


class NSEClient:
    """Network fetcher for downloading raw EOD Bhavcopy ZIP and Corporate Action files from NSE India."""

    BHAVCOPY_ZIP_URL_FMT = "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{trade_date}_F_0000.csv.zip"
    CORPORATE_ACTIONS_URL = "https://www.nseindia.com/api/corporates-corporateactions?index=equities"

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
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
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
        """Fetch unparsed NSE Corporate Action JSON/CSV bytes, validate headers/schema, and store in RawStore."""
        if mock_bytes is not None:
            raw_bytes = mock_bytes
        else:
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            try:
                # Try curl session initialization for NSE API
                cmd1 = ["curl", "-s", "-A", ua, "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "-c", "/tmp/nse_cookies.txt", "https://www.nseindia.com/"]
                subprocess.run(cmd1, timeout=10, capture_output=True)

                cmd2 = ["curl", "-s", "-A", ua, "-H", "Accept: application/json, text/plain, */*", "-b", "/tmp/nse_cookies.txt", self.CORPORATE_ACTIONS_URL]
                res = subprocess.run(cmd2, timeout=15, capture_output=True, check=True)
                raw_bytes = res.stdout
            except Exception:
                req = urllib.request.Request(
                    self.CORPORATE_ACTIONS_URL,
                    headers={"User-Agent": ua, "Accept": "application/json, text/csv, */*"},
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    raw_bytes = response.read()

        # Validate JSON or CSV content representation
        content_header = raw_bytes[:1024].decode("utf-8", errors="replace").strip()
        is_json = content_header.startswith("[") or content_header.startswith("{")
        if is_json:
            try:
                parsed = json.loads(raw_bytes)
                if not isinstance(parsed, (list, dict)):
                    raise ValueError("Parsed corporate action JSON is not list/dict")
            except Exception as err:
                raise ValueError(f"Invalid NSE Corporate Action JSON response: {err}") from err
        else:
            upper_header = content_header.upper()
            required_headers = ["SYMBOL", "PURPOSE", "EX-DATE"]
            missing = [h for h in required_headers if h not in upper_header and h.replace("-", "") not in upper_header]
            if missing:
                raise ValueError(f"Invalid NSE Corporate Action CSV response: missing required headers {missing}")

        filename = "corporate_actions_nse.json" if is_json else "corporate_actions_nse.csv"
        manifest = self.raw_store.put_raw(
            provider="nse",
            resource_type="corporate_actions",
            filename=filename,
            data=raw_bytes,
        )
        return raw_bytes, manifest
