"""
核心基础模块单元测试 — 限频器 (LLMRateLimiter)
覆盖: acquire/release/信号量/令牌桶/单例/并发/超时
"""
import pytest
import time
import threading
import concurrent.futures

from app.core.llm_rate_limiter import LLMRateLimiter


class TestRateLimiterBasic:
    def test_acquire_release(self):
        limiter = LLMRateLimiter(max_qps=10.0, max_concurrent=1)
        assert limiter.acquire(timeout=1.0)
        limiter.release()

    def test_acquire_increments_total_requests(self):
        limiter = LLMRateLimiter(max_qps=10.0, max_concurrent=1)
        limiter.acquire(timeout=1.0)
        limiter.release()
        stats = limiter.get_stats()
        assert stats["total_requests"] == 1

    def test_semaphore_blocks_beyond_max_concurrent(self):
        limiter = LLMRateLimiter(max_qps=999.0, max_concurrent=2)
        assert limiter.acquire(timeout=1.0)
        assert limiter.acquire(timeout=1.0)
        assert not limiter.acquire(timeout=0.1)
        limiter.release()
        limiter.release()

    def test_release_allows_next(self):
        limiter = LLMRateLimiter(max_qps=999.0, max_concurrent=1)
        limiter.acquire(timeout=1.0)
        limiter.release()
        assert limiter.acquire(timeout=1.0)
        limiter.release()


class TestRateLimiterSingleton:
    def test_configure_creates_new_instance(self):
        LLMRateLimiter.configure(max_qps=7.0, max_concurrent=3)
        inst = LLMRateLimiter.get_instance()
        stats = inst.get_stats()
        assert stats["max_qps"] == 7.0
        assert stats["max_concurrent"] == 3
        LLMRateLimiter.configure(max_qps=3.0, max_concurrent=5)

    def test_singleton_identity(self):
        inst1 = LLMRateLimiter.get_instance()
        inst2 = LLMRateLimiter.get_instance()
        assert inst1 is inst2


class TestRateLimiterStats:
    def test_stats_structure(self):
        limiter = LLMRateLimiter(max_qps=5.0, max_concurrent=3)
        stats = limiter.get_stats()
        assert "total_requests" in stats
        assert "total_waited_seconds" in stats
        assert "max_qps" in stats
        assert "max_concurrent" in stats
        assert stats["max_qps"] == 5.0
        assert stats["max_concurrent"] == 3


class TestRateLimiterConcurrency:
    def test_concurrent_acquire_never_exceeds_max(self):
        max_concurrent = 3
        limiter = LLMRateLimiter(max_qps=999.0, max_concurrent=max_concurrent)
        peak = 0
        current = 0
        lock = threading.Lock()

        def worker():
            nonlocal peak, current
            if limiter.acquire(timeout=5.0):
                with lock:
                    current += 1
                    peak = max(peak, current)
                time.sleep(0.05)
                with lock:
                    current -= 1
                limiter.release()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(worker) for _ in range(10)]
            concurrent.futures.wait(futures)

        assert peak <= max_concurrent

    def test_all_requests_succeed_with_enough_timeout(self):
        limiter = LLMRateLimiter(max_qps=999.0, max_concurrent=3)
        results = []

        def worker():
            ok = limiter.acquire(timeout=10.0)
            if ok:
                time.sleep(0.01)
                limiter.release()
            results.append(ok)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker) for _ in range(5)]
            concurrent.futures.wait(futures)

        assert all(results)
