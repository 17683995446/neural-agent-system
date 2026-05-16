"""
核心基础模块单元测试 — 熔断器 (CircuitBreaker)
覆盖: 正常调用/熔断触发/HALF_OPEN恢复/重置/线程安全/异常场景
"""
import pytest
import time
import threading

from app.core.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreakerNormal:
    def test_success_call(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)
        result = cb.call(lambda: 42)
        assert result == 42
        assert cb.state == CircuitState.CLOSED

    def test_success_increments_counter(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.call(lambda: 1)
        cb.call(lambda: 2)
        stats = cb.get_stats()
        assert stats["success_count"] == 2

    def test_fallback_on_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=10.0)
        def failing():
            raise ValueError("fail")
        try:
            cb.call(failing)
        except ValueError:
            pass
        assert cb.state == CircuitState.OPEN
        result = cb.call(lambda: "should_not_run", fallback=lambda: "fallback_used")
        assert result == "fallback_used"

    def test_fallback_none_on_open(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=10.0)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        result = cb.call(lambda: "x", fallback=None)
        assert result is None


class TestCircuitBreakerTripping:
    def test_trips_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)
        def fail():
            raise RuntimeError("fail")
        for _ in range(3):
            try:
                cb.call(fail)
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN

    def test_does_not_trip_before_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        assert cb.state == CircuitState.CLOSED

    def test_failure_count_resets_on_success(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=10.0)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        cb.call(lambda: "ok")
        stats = cb.get_stats()
        assert stats["failure_count"] == 0


class TestCircuitBreakerHalfOpen:
    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        time.sleep(0.15)
        cb.call(lambda: "ok")
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        time.sleep(0.15)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerReset:
    def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=10.0)
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        stats = cb.get_stats()
        assert stats["failure_count"] == 0
        assert stats["success_count"] == 0


class TestCircuitBreakerStats:
    def test_stats_structure(self):
        cb = CircuitBreaker("my_cb", failure_threshold=5, recovery_timeout=30.0)
        stats = cb.get_stats()
        assert stats["name"] == "my_cb"
        assert stats["state"] == "closed"
        assert stats["failure_threshold"] == 5
        assert stats["recovery_timeout"] == 30.0

    def test_stats_after_operations(self):
        cb = CircuitBreaker("test", failure_threshold=5, recovery_timeout=10.0)
        cb.call(lambda: "ok")
        try:
            cb.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        stats = cb.get_stats()
        assert stats["success_count"] == 1
        assert stats["failure_count"] == 1


class TestCircuitBreakerConcurrency:
    def test_concurrent_calls(self):
        cb = CircuitBreaker("test", failure_threshold=100, recovery_timeout=10.0)
        results = []
        errors = []

        def worker(val):
            try:
                r = cb.call(lambda: val * 2)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        assert len(errors) == 0
