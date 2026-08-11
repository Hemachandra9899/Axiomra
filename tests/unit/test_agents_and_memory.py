"""Regime, attribution, journal and agents unit tests."""

from __future__ import annotations

from datetime import UTC

from axiomra.agents.base import StructuredOutput
from axiomra.agents.fundamental import FundamentalAgent
from axiomra.agents.news import NewsAgent
from axiomra.agents.orchestrator import ResearchOrchestrator
from axiomra.agents.skeptic import SkepticReviewAgent
from axiomra.agents.technical import TechnicalAgent
from axiomra.domain.market import OHLCV, MarketSnapshot
from axiomra.domain.signals import EvidenceSignal, SkepticReview
from axiomra.memory.attribution import AttributionEngine
from axiomra.memory.journal import JournalEntry, MemoryJournal
from axiomra.regime.classifier import RegimeClassifier, classify_regime


def _snapshot() -> MarketSnapshot:
    from datetime import datetime

    return MarketSnapshot(
        symbol="ABC",
        timestamp=datetime.now(UTC),
        bar=OHLCV(open=100, high=105, low=99, close=102, volume=1_000_000),
        features={
            "momentum_5d": 0.04,
            "momentum_20d": 0.10,
            "distance_ema20": 0.03,
            "rsi_14": 62.0,
            "atr_14": 3.0,
            "volume_ratio": 1.2,
            "momentum_60d": 0.20,
        },
        fundamentals={"roe": 18.0, "pe": 25.0, "debt_equity": 0.3},
        data_version="test-v1",
    )


def test_regime_classifier():
    assert classify_regime(105, 102, 100, 0.02) == "TREND_UP"
    assert classify_regime(95, 97, 100, 0.02) == "TREND_DOWN"
    assert classify_regime(101, 102, 101, 0.02) == "RANGE"
    assert classify_regime(105, 102, 100, 0.50) == "HIGH_VOL"


def test_regime_classifier_instance():
    cls = RegimeClassifier(high_vol_threshold=0.4)
    assert cls.classify(105, 102, 100, 0.5) == "HIGH_VOL"


def test_attribution_learns_reliability():
    engine = AttributionEngine()
    engine.record(
        [
            EvidenceSignal(source="quant", score=0.8, confidence=0.9),
            EvidenceSignal(source="news", score=-0.6, confidence=0.8),
        ],
        outcome_return_pct=3.2,
    )
    engine.record(
        [EvidenceSignal(source="quant", score=0.7, confidence=0.9)],
        outcome_return_pct=-2.0,
    )
    rel = engine.reliability()
    assert rel["quant"] == pytest_approx(0.5)
    assert rel["news"] == 0.0  # news was bearish, outcome was positive
    assert engine.by_source("unknown").observations == 0


def pytest_approx(x):
    from pytest import approx

    return approx(x)


def test_memory_journal_immutable_records():
    from datetime import datetime

    journal = MemoryJournal()
    eid = journal.record(
        JournalEntry(
            decision_id="d1",
            symbol="ABC",
            timestamp=datetime.now(UTC),
            data_version="v1",
            feature_version="f1",
            combined_score=0.7,
        )
    )
    assert journal.get("d1") is not None
    assert journal.count() == 1
    assert eid == "d1"


def test_skeptic_reduces_confidence():
    review = SkepticReview(severity=0.4, objections=["overvaluation"])
    assert review.has_objections
    assert review.confidence_multiplier == pytest_approx(0.6)


def _reasoner(output: StructuredOutput):
    async def reasoner(system_prompt, context):
        return output

    return reasoner


async def test_agents_produce_structured_evidence():
    snapshot = _snapshot()
    technical = TechnicalAgent(_reasoner(StructuredOutput(score=0.6, confidence=0.8)))
    fundamental = FundamentalAgent(_reasoner(StructuredOutput(score=0.4, confidence=0.7)))
    news = NewsAgent(_reasoner(StructuredOutput(score=-0.1, confidence=0.5)))

    signals = [
        await technical.analyze(snapshot),
        await fundamental.analyze(snapshot),
        await news.analyze(snapshot),
    ]
    assert [s.source for s in signals] == ["technical", "fundamental", "news"]
    assert all(s.score >= -1 and s.score <= 1 for s in signals)


async def test_orchestrator_is_resilient_to_agent_failure():
    class Broken:
        name = "broken"

        async def analyze(self, snapshot):
            raise RuntimeError("boom")

    orch = ResearchOrchestrator(agents=[Broken()])
    signals = await orch.research(_snapshot())
    assert len(signals) == 1
    assert signals[0].confidence == 0.0


async def test_skeptic_agent_review():
    skeptic = SkepticReviewAgent(_reasoner(StructuredOutput(score=0, confidence=1.0)))
    review = await skeptic.review(_snapshot(), EvidenceSignal(source="quant", score=0.8, confidence=0.9))
    assert isinstance(review, SkepticReview)
