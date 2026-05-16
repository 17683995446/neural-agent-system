"""
核心基础模块单元测试 — AgentPool
覆盖: dispatch/dispatch_simple/优先级/聚合/统计
"""
import pytest
import time
from unittest.mock import MagicMock

from app.core.agent_pool import AgentPool, AgentPriority, AgentTask, AgentResult


class TestAgentResult:
    def test_default_values(self):
        r = AgentResult(agent_id="a1")
        assert r.result is None
        assert r.error is None
        assert r.duration_ms == 0.0
        assert r.confidence == 0.0
        assert r.priority == AgentPriority.NORMAL

    def test_with_values(self):
        r = AgentResult(agent_id="a1", result={"k": "v"}, duration_ms=100.0, confidence=0.9)
        assert r.result == {"k": "v"}
        assert r.confidence == 0.9


class TestAgentTask:
    def test_default_values(self):
        t = AgentTask(task_id="t1", func=lambda: None)
        assert t.args == ()
        assert t.kwargs == {}
        assert t.priority == AgentPriority.NORMAL
        assert t.timeout == 30.0

    def test_with_values(self):
        t = AgentTask(task_id="t1", func=sum, args=([1, 2],), priority=AgentPriority.CRITICAL)
        assert t.args == ([1, 2],)
        assert t.priority == AgentPriority.CRITICAL


class TestAgentPriority:
    def test_ordering(self):
        assert AgentPriority.CRITICAL < AgentPriority.NORMAL < AgentPriority.LOW


class TestAgentPoolBasic:
    def test_dispatch_simple(self):
        pool = AgentPool(max_workers=2)
        results = pool.dispatch_simple(lambda x: x * 2, [1, 2, 3])
        assert len(results) == 3
        assert all(r.error is None for r in results)

    def test_dispatch_simple_with_exception(self):
        pool = AgentPool(max_workers=2)
        def transform(x):
            if x == 1:
                raise ValueError("test error")
            return x
        results = pool.dispatch_simple(transform, [1, 2])
        assert len(results) == 2
        ok_results = [r for r in results if r.error is None]
        fail_results = [r for r in results if r.error is not None]
        assert len(ok_results) == 1
        assert len(fail_results) == 1

    def test_dispatch_with_tasks(self):
        pool = AgentPool(max_workers=2)
        tasks = [
            AgentTask(task_id="t1", func=lambda x: x * 2, args=(5,)),
            AgentTask(task_id="t2", func=lambda x: x + 1, args=(10,)),
        ]
        results = pool.dispatch(tasks)
        assert len(results) == 2


class TestAgentPoolStats:
    def test_stats_structure(self):
        pool = AgentPool(max_workers=4)
        stats = pool.get_stats()
        assert "total_dispatched" in stats
        assert "total_success" in stats
        assert "total_failed" in stats
        assert "success_rate" in stats

    def test_stats_after_dispatch(self):
        pool = AgentPool(max_workers=2)
        pool.dispatch_simple(lambda x: x, [1, 2])
        stats = pool.get_stats()
        assert stats["total_dispatched"] == 2
        assert stats["total_success"] == 2


class TestAgentPoolAggregate:
    def test_aggregate_default_strategy(self):
        pool = AgentPool(max_workers=1)
        results = [
            AgentResult(agent_id="a1", result="answer_a", confidence=0.9),
            AgentResult(agent_id="a2", result="answer_b", confidence=0.8),
        ]
        aggregated = pool.aggregate(results)
        assert aggregated is not None
        assert len(aggregated) == 2

    def test_aggregate_empty(self):
        pool = AgentPool(max_workers=1)
        result = pool.aggregate([])
        assert result == []
