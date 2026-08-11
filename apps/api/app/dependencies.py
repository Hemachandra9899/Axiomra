"""Dependency wiring placeholder for the API app.

In production this module builds the real component graph: market provider,
repository, quant models, agents, fusion, portfolio, risk and execution.
"""

from __future__ import annotations


def build_pipeline():  # pragma: no cover
    raise NotImplementedError("Wire real providers and models here")
