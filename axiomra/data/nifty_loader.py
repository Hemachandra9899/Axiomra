"""NSE Indices Source Loader for downloading raw NIFTY constituent and reconstitution sources."""

from __future__ import annotations

import urllib.request

from axiomra.storage.raw import RawFetchManifest, RawStore


class NSEIndicesSourceLoader:
    """Network fetcher and source loader for NIFTY constituent files and reconstitution notices."""

    NIFTY200_CSV_URL = "https://niftyindices.com/IndexConstituent/ind_nifty200list.csv"

    def __init__(self, raw_store: RawStore | None = None) -> None:
        self.raw_store = raw_store or RawStore()

    def fetch_index_constituents_bytes(
        self,
        index_name: str = "NIFTY 200",
        mock_bytes: bytes | None = None,
    ) -> tuple[bytes, RawFetchManifest]:
        """Fetch raw NIFTY constituent CSV/JSON bytes and store in RawStore with manifest."""
        if mock_bytes is not None:
            raw_bytes = mock_bytes
        else:
            req = urllib.request.Request(
                self.NIFTY200_CSV_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_bytes = response.read()

        filename = f"constituents_{index_name.lower().replace(' ', '_')}.csv"
        manifest = self.raw_store.put_raw(
            provider="nifty_indices",
            resource_type="membership_sources",
            filename=filename,
            data=raw_bytes,
            request_parameters={"index_name": index_name},
        )
        return raw_bytes, manifest
