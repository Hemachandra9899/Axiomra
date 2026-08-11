"""Dataset Builder exception hierarchy."""

from __future__ import annotations


class DatasetBuildError(Exception):
    """Base exception for dataset build failures."""


class CoverageGateFailedError(DatasetBuildError):
    """Raised when instrument coverage falls below required threshold."""


class ReconciliationFailedError(DatasetBuildError):
    """Raised when primary and secondary provider reconciliation fails."""


class InstrumentResolutionFailedError(DatasetBuildError):
    """Raised when an instrument symbol cannot be resolved to a canonical Instrument ID."""


class IncompleteRunError(DatasetBuildError):
    """Raised when a dataset build run aborts due to partial acquisition or missing instruments."""


class MissingProviderCredentialsError(DatasetBuildError):
    """Raised when required provider API credentials (e.g. UPSTOX_ACCESS_TOKEN) are missing."""


class CorporateActionFetchError(DatasetBuildError):
    """Raised when corporate action acquisition or parsing fails for adjusted datasets."""
