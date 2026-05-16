"""
LLMResponseCache — LLM响应缓存
- 基于prompt内容的SHA256 hash
- 内存缓存, TTL过期
- LRU淘汰
- 统计命中率
"""
import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class LLMResponseCache:
    def __init__(self, ttl_seconds: float = 3600, max_size: int = 500):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, messages: List[Dict], **kwargs: Any) -> Optional[Any]:
        key = self._make_key(messages, kwargs)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                result, timestamp = entry
                if time.monotonic() - timestamp < self._ttl:
                    self._hits += 1
                    return result
                else:
                    del self._cache[key]
            self._misses += 1
            return None

    def put(self, messages: List[Dict], result: Any, **kwargs: Any):
        key = self._make_key(messages, kwargs)
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (result, time.monotonic())

    def invalidate(self, messages: List[Dict], **kwargs: Any):
        key = self._make_key(messages, kwargs)
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @staticmethod
    def _make_key(messages: List[Dict], kwargs: Dict) -> str:
        content = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        kw_str = json.dumps(kwargs, sort_keys=True, default=str)
        return hashlib.sha256((content + kw_str).encode()).hexdigest()[:32]

    def get_stats(self) -> Dict:
        total = self._hits + self._misses
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
                "cache_size": len(self._cache),
            }
