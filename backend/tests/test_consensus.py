"""
核心基础模块单元测试 — 共识引擎 (ConsensusEngine)
覆盖: 4种策略/等价类划分/多样性/置信度/边界条件
"""
import pytest
from app.core.consensus import (
    ConsensusEngine,
    ConsensusStrategy,
    ConsensusReport,
    EquivalenceClass,
)


class TestConsensusEngineStrict:
    def test_identical_strings_consensus(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.STRICT_MATCH, consensus_threshold=0.6)
        report = engine.evaluate(["hello", "hello", "hello"])
        assert report.has_consensus
        assert report.consensus_result == "hello"
        assert report.consensus_ratio == 1.0

    def test_all_different_no_consensus(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.STRICT_MATCH, consensus_threshold=0.6)
        report = engine.evaluate(["a", "b", "c"])
        assert not report.has_consensus

    def test_majority_consensus(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.STRICT_MATCH, consensus_threshold=0.6)
        report = engine.evaluate(["a", "a", "b"])
        assert report.has_consensus
        assert report.consensus_result == "a"
        assert abs(report.consensus_ratio - 2/3) < 1e-9

    def test_empty_candidates(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.STRICT_MATCH)
        report = engine.evaluate([])
        assert not report.has_consensus

    def test_single_candidate(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.STRICT_MATCH)
        report = engine.evaluate(["only"])
        assert report.has_consensus
        assert report.consensus_result == "only"
        assert report.consensus_ratio == 1.0


class TestConsensusEngineNormalized:
    def test_whitespace_normalized(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.NORMALIZED_MATCH, consensus_threshold=0.6)
        report = engine.evaluate(["  hello  ", "hello", "\nhello\n"])
        assert report.has_consensus

    def test_case_not_normalized_by_default(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.NORMALIZED_MATCH, consensus_threshold=0.6)
        report = engine.evaluate(["Hello", "hello", "HELLO"])
        assert report.total_candidates == 3


class TestConsensusEngineOverlap:
    def test_overlapping_code_consensus(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.OVERLAP_RATIO, consensus_threshold=0.6)
        code1 = "def add(a, b):\n    return a + b\n"
        code2 = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
        report = engine.evaluate([code1, code2])
        assert report.total_candidates == 2

    def test_non_overlapping_no_consensus(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.OVERLAP_RATIO, consensus_threshold=0.6)
        report = engine.evaluate(["completely different content", "no overlap at all here"])
        assert not report.has_consensus


class TestConsensusEngineStructure:
    def test_same_structure_consensus(self):
        engine = ConsensusEngine(strategy=ConsensusStrategy.STRUCTURE_SIMILARITY, consensus_threshold=0.6)
        report = engine.evaluate([
            {"type": "function", "name": "add", "params": 2},
            {"type": "function", "name": "add", "params": 2},
        ])
        assert report.has_consensus


class TestConsensusReport:
    def test_report_fields(self):
        report = ConsensusReport(
            has_consensus=True,
            consensus_result="test",
            consensus_ratio=0.8,
            total_candidates=3,
            strategy_used="strict_match",
        )
        assert report.has_consensus
        assert report.consensus_result == "test"
        assert report.consensus_ratio == 0.8
        assert report.total_candidates == 3

    def test_default_values(self):
        report = ConsensusReport(has_consensus=False)
        assert report.consensus_result is None
        assert report.consensus_ratio == 0.0
        assert report.equivalence_classes == []
        assert report.dissent_items == []
        assert report.diversity_score == 0.0


class TestEquivalenceClass:
    def test_basic(self):
        eq = EquivalenceClass(representative="a", members=[0, 1], member_results=["a", "a"], size=2)
        assert eq.representative == "a"
        assert eq.size == 2
        assert len(eq.members) == 2
