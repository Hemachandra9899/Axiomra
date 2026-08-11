"""Dataset Builder Exception Types."""

from __future__ import annotations


class DatasetBuildError(Exception):
    """Base exception for all dataset build failures."""


class CoverageGateFailedError(DatasetBuildError):
    """Raised when coverage audit fails minimum session ratio requirements."""


class ReconciliationFailedError(DatasetBuildError):
    """Raised when provider cross-reconciliation detects unresolvable discrepancies."""


class InstrumentResolutionFailedError(DatasetBuildError):
    """Raised when one or more universe symbols cannot be resolved in InstrumentMaster."""


class IncompleteRunError(DatasetBuildError):
    """Raised when an acquisition run fails for one or more requested instruments."""
