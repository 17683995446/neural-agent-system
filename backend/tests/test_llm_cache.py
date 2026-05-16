"""
核心基础模块单元测试 — LLM响应缓存 (LLMResponseCache)
覆盖: get/put/invalidate/clear/TTL过期/LRU淘汰/并发/统计
"""
import pytest
import time
import threading

from app.core.llm_cache import LLMResponseCache


class TestCacheBasic:
    def test_put_and_get(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs = [{"role": "user", "content": "hello"}]
        cache.put(msgs, {"reply": "world"})
        result = cache.get(msgs)
        assert result == {"reply": "world"}

    def test_miss_returns_none(self):
        cache = LLMResponseCache(ttl_seconds=60)
        result = cache.get([{"role": "user", "content": "no"}])
        assert result is None

    def test_different_messages_different_keys(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs1 = [{"role": "user", "content": "hello"}]
        msgs2 = [{"role": "user", "content": "world"}]
        cache.put(msgs1, {"r": 1})
        cache.put(msgs2, {"r": 2})
        assert cache.get(msgs1) == {"r": 1}
        assert cache.get(msgs2) == {"r": 2}

    def test_kwargs_affect_key(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs = [{"role": "user", "content": "hi"}]
        cache.put(msgs, {"r": "default"})
        cache.put(msgs, {"r": "model_a"}, model="a")
        assert cache.get(msgs) == {"r": "default"}
        assert cache.get(msgs, model="a") == {"r": "model_a"}


class TestCacheTTL:
    def test_expired_entry_returns_none(self):
        cache = LLMResponseCache(ttl_seconds=0.1)
        msgs = [{"role": "user", "content": "hi"}]
        cache.put(msgs, {"r": 1})
        assert cache.get(msgs) == {"r": 1}
        time.sleep(0.15)
        assert cache.get(msgs) is None


class TestCacheLRU:
    def test_max_size_eviction(self):
        cache = LLMResponseCache(ttl_seconds=60, max_size=2)
        cache.put([{"role": "user", "content": "a"}], {"r": "a"})
        cache.put([{"role": "user", "content": "b"}], {"r": "b"})
        cache.put([{"role": "user", "content": "c"}], {"r": "c"})
        assert cache.get([{"role": "user", "content": "a"}]) is None
        assert cache.get([{"role": "user", "content": "b"}]) == {"r": "b"}
        assert cache.get([{"role": "user", "content": "c"}]) == {"r": "c"}


class TestCacheInvalidate:
    def test_invalidate_specific(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs = [{"role": "user", "content": "hi"}]
        cache.put(msgs, {"r": 1})
        cache.invalidate(msgs)
        assert cache.get(msgs) is None

    def test_invalidate_nonexistent(self):
        cache = LLMResponseCache(ttl_seconds=60)
        cache.invalidate([{"role": "user", "content": "no"}])


class TestCacheClear:
    def test_clear(self):
        cache = LLMResponseCache(ttl_seconds=60)
        cache.put([{"role": "user", "content": "a"}], {"r": "a"})
        cache.put([{"role": "user", "content": "b"}], {"r": "b"})
        cache.clear()
        stats_after_clear = cache.get_stats()
        assert stats_after_clear["hits"] == 0
        assert stats_after_clear["misses"] == 0
        assert cache.get([{"role": "user", "content": "a"}]) is None
        assert cache.get([{"role": "user", "content": "b"}]) is None


class TestCacheStats:
    def test_hit_miss_tracking(self):
        cache = LLMResponseCache(ttl_seconds=60)
        msgs = [{"role": "user", "content": "hi"}]
        cache.put(msgs, {"r": 1})
        cache.get(msgs)
        cache.get([{"role": "user", "content": "no"}])
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_size(self):
        cache = LLMResponseCache(ttl_seconds=60, max_size=100)
        for i in range(5):
            cache.put([{"role": "user", "content": f"msg{i}"}], {"r": i})
        stats = cache.get_stats()
        assert stats["cache_size"] == 5


class TestCacheConcurrency:
    def test_concurrent_access(self):
        cache = LLMResponseCache(ttl_seconds=60, max_size=100)
        errors = []

        def writer(idx):
            try:
                cache.put([{"role": "user", "content": f"w{idx}"}], {"r": idx})
            except Exception as e:
                errors.append(e)

        def reader(idx):
            try:
                cache.get([{"role": "user", "content": f"w{idx}"}])
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(20):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
