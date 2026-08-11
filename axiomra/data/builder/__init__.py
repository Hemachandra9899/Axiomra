"""Axiomra Dataset Builder Package."""

from axiomra.data.builder.builder import DatasetBuilder, DatasetBuildResult
from axiomra.data.builder.config import DatasetBuildConfig
from axiomra.data.builder.errors import (
    CoverageGateFailedError,
    DatasetBuildError,
    IncompleteRunError,
    InstrumentResolutionFailedError,
    ReconciliationFailedError,
)
from axiomra.data.builder.report import BuildRunManifest, DatasetBuildReport
from axiomra.data.builder.stage_a_fixture import run_stage_a_fixture
from axiomra.data.builder.stage_a_real import run_stage_a_real_build
from axiomra.data.builder.stage_b_fixture import run_stage_b_fixture
from axiomra.data.builder.stage_b_real import run_stage_b_real_build
from axiomra.data.builder.stage_c_fixture import run_stage_c_fixture
from axiomra.data.builder.stage_c_real import run_stage_c_real_build

__all__ = [
    "BuildRunManifest",
    "CoverageGateFailedError",
    "DatasetBuildConfig",
    "DatasetBuildError",
    "DatasetBuildReport",
    "DatasetBuildResult",
    "DatasetBuilder",
    "IncompleteRunError",
    "InstrumentResolutionFailedError",
    "ReconciliationFailedError",
    "run_stage_a_fixture",
    "run_stage_a_real_build",
    "run_stage_b_fixture",
    "run_stage_b_real_build",
    "run_stage_c_fixture",
    "run_stage_c_real_build",
]
