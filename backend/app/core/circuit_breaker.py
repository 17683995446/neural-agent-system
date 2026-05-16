"""
CircuitBreaker — 熔断器
- 连续N次失败 → 熔断(OPEN), 直接返回fallback
- 等待recovery_timeout → 半开(HALF_OPEN), 允许1个请求试探
- 试探成功 → 恢复(CLOSED)
- 试探失败 → 继续熔断(OPEN)
"""
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional

from app.core.logging import logger


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time > self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def call(
        self,
        func: Callable,
        *args: Any,
        fallback: Optional[Callable] = None,
        **kwargs: Any,
    ) -> Any:
        current_state = self.state

        if current_state == CircuitState.OPEN:
            logger.warning("Circuit [%s] is OPEN, using fallback", self._name)
            return fallback() if callable(fallback) else fallback

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if current_state == CircuitState.HALF_OPEN:
                logger.error("Circuit [%s] HALF_OPEN probe failed: %s", self._name, e)
            raise

    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._success_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit [%s] recovered to CLOSED", self._name)

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    "Circuit [%s] blown to OPEN after %d failures",
                    self._name, self._failure_count,
                )

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "name": self._name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout": self._recovery_timeout,
            }

    def reset(self):
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
