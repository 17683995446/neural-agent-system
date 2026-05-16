"""
核心基础模块单元测试 — 短期记忆 (ShortTermMemory)
使用mock redis，覆盖: save/get/trust_filter/context/clear
"""
import pytest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime

from app.agents.memory.short_term import ShortTermMemory


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.hset = MagicMock(return_value=True)
    r.hgetall = MagicMock(return_value={})
    r.set = MagicMock(return_value=True)
    r.get = MagicMock(return_value=None)
    r.delete = MagicMock(return_value=True)
    r.keys = MagicMock(return_value=[])
    r.expire = MagicMock(return_value=True)
    return r


@pytest.fixture
def stm(mock_redis):
    return ShortTermMemory(task_id="test-task-001", redis_client=mock_redis)


class TestShortTermMemoryMessage:
    def test_save_message(self, stm, mock_redis):
        ok = stm.save_message("agent_a", {"data": "hello"})
        assert ok
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    def test_get_message_exists(self, stm, mock_redis):
        stored = {"data": "hello"}
        mock_redis.hgetall.return_value = {
            "message": json.dumps(stored),
            "update_time": datetime.now().isoformat(),
        }
        result = stm.get_message("agent_a")
        assert result == stored

    def test_get_message_missing(self, stm, mock_redis):
        mock_redis.hgetall.return_value = {}
        result = stm.get_message("agent_a")
        assert result is None

    def test_get_message_redis_error(self, stm, mock_redis):
        mock_redis.hgetall.side_effect = Exception("redis down")
        result = stm.get_message("agent_a")
        assert result is None


class TestShortTermMemoryTrust:
    def test_save_trust_matrix(self, stm, mock_redis):
        ok = stm.save_trust_matrix("agent_a", {"upper_b": 1.5})
        assert ok
        mock_redis.set.assert_called_once()

    def test_get_trust_matrix_exists(self, stm, mock_redis):
        trust = {"upper_b": 1.5}
        mock_redis.get.return_value = json.dumps(trust)
        result = stm.get_trust_matrix("agent_a")
        assert result == trust

    def test_get_trust_matrix_missing(self, stm, mock_redis):
        mock_redis.get.return_value = None
        result = stm.get_trust_matrix("agent_a")
        assert result == {}

    def test_get_trust_matrix_error(self, stm, mock_redis):
        mock_redis.get.side_effect = Exception("error")
        result = stm.get_trust_matrix("agent_a")
        assert result == {}


class TestShortTermMemoryTrustFilter:
    def test_filter_keeps_high_trust(self):
        stm = ShortTermMemory(task_id="t1", redis_client=MagicMock())
        messages = [
            {"sender_agent_id": "a", "content": "high"},
            {"sender_agent_id": "b", "content": "low"},
            {"sender_agent_id": "c", "content": "medium"},
        ]
        trust = {"a": 0.9, "b": 0.3, "c": 0.6}
        result = stm.filter_by_trust(messages, trust)
        assert len(result) == 2
        assert result[0]["content"] == "high"
        assert result[1]["content"] == "medium"

    def test_filter_empty_trust_returns_all(self):
        stm = ShortTermMemory(task_id="t1", redis_client=MagicMock())
        messages = [{"sender_agent_id": "a"}, {"sender_agent_id": "b"}]
        result = stm.filter_by_trust(messages, {})
        assert len(result) == 2

    def test_filter_all_below_threshold(self):
        stm = ShortTermMemory(task_id="t1", redis_client=MagicMock())
        messages = [{"sender_agent_id": "a"}, {"sender_agent_id": "b"}]
        trust = {"a": 0.1, "b": 0.2}
        result = stm.filter_by_trust(messages, trust)
        assert len(result) == 0

    def test_filter_missing_sender_default_trust_1(self):
        stm = ShortTermMemory(task_id="t1", redis_client=MagicMock())
        messages = [{"sender_agent_id": "unknown", "content": "x"}]
        trust = {"a": 0.9}
        result = stm.filter_by_trust(messages, trust)
        assert len(result) == 1


class TestShortTermMemoryContext:
    def test_save_context(self, stm, mock_redis):
        ok = stm.save_context("agent_a", {"key": "val"})
        assert ok

    def test_get_context_exists(self, stm, mock_redis):
        ctx = {"key": "val"}
        mock_redis.get.return_value = json.dumps(ctx)
        result = stm.get_context("agent_a")
        assert result == ctx

    def test_get_context_missing(self, stm, mock_redis):
        mock_redis.get.return_value = None
        result = stm.get_context("agent_a")
        assert result is None


class TestShortTermMemoryClear:
    def test_clear_specific_agent(self, stm, mock_redis):
        ok = stm.clear(agent_id="agent_a")
        assert ok
        mock_redis.delete.assert_called_once()

    def test_clear_all(self, stm, mock_redis):
        mock_redis.keys.return_value = ["st:task:test-task-001:a", "st:task:test-task-001:b"]
        ok = stm.clear()
        assert ok
        mock_redis.delete.assert_called_once()

    def test_clear_redis_error(self, stm, mock_redis):
        mock_redis.delete.side_effect = Exception("redis down")
        result = stm.clear(agent_id="agent_a")
        assert result is False
