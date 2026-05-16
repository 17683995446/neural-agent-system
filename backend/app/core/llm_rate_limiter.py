"""
LLMRateLimiter — 令牌桶限频器
- max_qps: 每秒最大请求数(控制429)
- max_concurrent: 最大并发数(控制负载)
"""
import threading
import time
from typing import Dict, Optional

from app.core.logging import logger


class LLMRateLimiter:
    _instance: Optional["LLMRateLimiter"] = None
    _init_lock = threading.Lock()

    def __init__(self, max_qps: float = 3.0, max_concurrent: int = 5):
        self._max_qps = max_qps
        self._max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)
        self._tokens = max_qps
        self._last_refill = time.monotonic()
        self._total_requests = 0
        self._total_waited = 0.0
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "LLMRateLimiter":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls(max_qps=3.0, max_concurrent=5)
        return cls._instance

    @classmethod
    def configure(cls, max_qps: float, max_concurrent: int):
        with cls._init_lock:
            cls._instance = cls(max_qps=max_qps, max_concurrent=max_concurrent)

    def acquire(self, timeout: float = 300.0) -> bool:
        deadline = time.monotonic() + timeout

        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            logger.warning("LLM rate limiter: concurrent limit reached")
            return False

        try:
            while True:
                with self._lock:
                    now = time.monotonic()
                    elapsed = now - self._last_refill
                    self._tokens = min(self._max_qps, self._tokens + elapsed * self._max_qps)
                    self._last_refill = now

                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        self._total_requests += 1
                        return True

                    wait = (1.0 - self._tokens) / self._max_qps

                if time.monotonic() + wait > deadline:
                    self._semaphore.release()
                    logger.warning("LLM rate limiter: timeout waiting for token")
                    return False

                time.sleep(wait)
                self._total_waited += wait
        except Exception:
            self._semaphore.release()
            return False

    def release(self):
        self._semaphore.release()

    def get_stats(self) -> Dict:
        return {
            "total_requests": self._total_requests,
            "total_waited_seconds": self._total_waited,
            "max_qps": self._max_qps,
            "max_concurrent": self._max_concurrent,
        }
