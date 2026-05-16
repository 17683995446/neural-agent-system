"""
LLM客户端 - 支持Anthropic API调用，含降级/fallback机制
同步complete()和异步acomplete()均集成限频+熔断+缓存
"""
import time
import asyncio
import random
import threading
from typing import Optional, List, Dict, Any

import requests

from app.core.config import settings
from app.core.logging import logger
from app.core.llm_rate_limiter import LLMRateLimiter
from app.core.circuit_breaker import CircuitBreaker
from app.core.llm_cache import LLMResponseCache

_RETRY_STATUS_CODES = {429, 500, 502, 503, 529}
_MAX_RETRIES = 3
_BASE_RETRY_DELAY = 1
_MAX_RETRY_DELAY = 30


def exponential_backoff(attempt: int) -> float:
    """指数退避策略"""
    delay = min(_BASE_RETRY_DELAY * (2 ** attempt), _MAX_RETRY_DELAY)
    return delay + random.uniform(0, 0.5)


class LLMClient:
    """LLM客户端封装 - 支持降级/fallback"""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 120.0
    ):
        # 优先使用Anthropic配置
        self.model = (
            model
            or settings.anthropic_model
            or settings.litellm_model
            or settings.default_llm_model
        )
        self.api_key = (
            api_key
            or settings.anthropic_auth_token
            or settings.litellm_api_key
            or settings.openai_api_key
        )
        self.api_base = (
            api_base
            or settings.anthropic_base_url
            or settings.litellm_api_base
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._available: Optional[bool] = None
        self._total_tokens: int = 0
        self._total_cost: float = 0.0
        self._rate_limiter = LLMRateLimiter.get_instance()
        self._circuit = CircuitBreaker("llm", failure_threshold=5, recovery_timeout=60)
        self._cache = LLMResponseCache(ttl_seconds=3600, max_size=500)

    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._available = bool(self.api_key)
        return self._available

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_cost(self) -> float:
        return self._total_cost

    def _estimate_cost(self, usage: Dict[str, Any]) -> float:
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return (prompt_tokens * 0.01 + completion_tokens * 0.03) / 1000

    def _update_usage(self, response: Dict[str, Any]):
        try:
            usage = response.get("usage", {})
            if usage:
                self._total_tokens += usage.get("total_tokens", 0)
                self._total_cost += self._estimate_cost(usage)
        except Exception as e:
            logger.debug(f"Usage update skipped: {e}")

    def _build_url(self) -> str:
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        import re
        if re.search(r"/v\d+$", base):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _make_request(self, messages: List[Dict[str, str]], **kwargs) -> requests.Response:
        """发送请求到LLM API（含限频）"""
        if not self._rate_limiter.acquire(timeout=300):
            raise requests.exceptions.RequestException("LLM rate limit timeout")
        try:
            url = self._build_url()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens)
            }
            return requests.post(url, headers=headers, json=payload, timeout=(10, self.timeout))
        finally:
            self._rate_limiter.release()

    def complete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        fallback_text: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        同步调用LLM，失败时返回fallback
        集成: 限频 + 熔断 + 响应缓存
        """
        if not self.is_available:
            logger.warning("[LLM] No API key configured, using fallback")
            return self._make_fallback_response(fallback_text)

        cached = self._cache.get(messages, model=model, **kwargs)
        if cached is not None:
            logger.debug("[LLM] Cache hit")
            return cached

        return self._circuit.call(
            self._complete_internal,
            messages, model, fallback_text, **kwargs,
            fallback=lambda: self._make_fallback_response(fallback_text),
        )

    def _complete_internal(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        fallback_text: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """实际重试逻辑（限频+熔断已在外层处理）"""
        target_model = model or self.model
        original_model = self.model
        if model:
            with self._rate_limiter._lock:
                self.model = model

        last_error: Optional[Exception] = None
        try:
            for attempt in range(_MAX_RETRIES):
                try:
                    logger.debug(f"[LLM] Calling model: {target_model} (attempt {attempt + 1}/{_MAX_RETRIES})")
                    response = self._make_request(messages, **kwargs)

                    if response.status_code in _RETRY_STATUS_CODES:
                        last_error = requests.exceptions.HTTPError(
                            f"HTTP {response.status_code}: {response.text[:200]}"
                        )
                        wait = exponential_backoff(attempt)
                        logger.warning(f"[LLM] Rate limited ({response.status_code}), retrying in {wait:.1f}s...")
                        time.sleep(wait)
                        continue

                    response.raise_for_status()
                    result = response.json()
                    self._update_usage(result)
                    self._available = True
                    self._cache.put(messages, result, model=model, **kwargs)
                    logger.debug("[LLM] Response received (cached)")
                    return result

                except requests.exceptions.RequestException as e:
                    last_error = e
                    if attempt < _MAX_RETRIES - 1:
                        wait = exponential_backoff(attempt)
                        logger.warning(f"[LLM] Request error, retrying in {wait:.1f}s: {e}")
                        time.sleep(wait)
                    else:
                        logger.error(f"[LLM] All retries exhausted: {e}")
        finally:
            with self._rate_limiter._lock:
                self.model = original_model

        self._available = False
        if last_error is None:
            last_error = requests.exceptions.RequestException("All retry attempts failed with no specific error")
        if fallback_text:
            logger.info("[LLM] Using fallback text after retries")
            return self._make_fallback_response(fallback_text)
        raise last_error

    async def acomplete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        fallback_text: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """异步调用LLM，集成限频+熔断+缓存（与complete()对齐）"""
        import aiohttp

        if not self.is_available:
            logger.warning("[LLM] No API key configured, using fallback")
            return self._make_fallback_response(fallback_text)

        cached = self._cache.get(messages, model=model, **kwargs)
        if cached is not None:
            logger.debug("[LLM] Async cache hit")
            return cached

        current_state = self._circuit.state
        from app.core.circuit_breaker import CircuitState
        if current_state == CircuitState.OPEN:
            logger.warning("[LLM] Async circuit breaker OPEN, using fallback")
            return self._make_fallback_response(fallback_text)

        acquired = await self._async_acquire(timeout=5.0)
        if not acquired:
            logger.warning("[LLM] Async rate limit timeout, using fallback")
            if fallback_text:
                return self._make_fallback_response(fallback_text)
            return self._make_fallback_response("")

        try:
            result = await self._acomplete_internal(messages, model, fallback_text, **kwargs)
            self._circuit._on_success()
            return result
        except Exception as e:
            self._circuit._on_failure()
            if fallback_text:
                logger.info("[LLM] Async using fallback after error: %s", e)
                return self._make_fallback_response(fallback_text)
            raise
        finally:
            self._rate_limiter.release()

    async def _async_acquire(self, timeout: float = 5.0) -> bool:
        """异步获取限频器许可 — 在线程池中执行同步acquire避免阻塞事件循环"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._rate_limiter.acquire, timeout)

    async def _acomplete_internal(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        fallback_text: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """异步内部重试逻辑（限频+熔断+缓存已在外层处理）"""
        import aiohttp

        target_model = model or self.model
        url = self._build_url()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens)
        }

        last_error: Optional[Exception] = None
        timeout_secs = aiohttp.ClientTimeout(sock_connect=10, total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout_secs) as session:
            for attempt in range(_MAX_RETRIES):
                try:
                    logger.debug(f"[LLM] Async calling model: {target_model} (attempt {attempt + 1}/{_MAX_RETRIES})")
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            self._update_usage(result)
                            self._available = True
                            self._cache.put(messages, result, model=model, **kwargs)
                            logger.debug("[LLM] Async response received (cached)")
                            return result
                        elif resp.status in _RETRY_STATUS_CODES:
                            body = await resp.text()
                            last_error = Exception(f"HTTP {resp.status}: {body[:200]}")
                            wait = exponential_backoff(attempt)
                            logger.warning(f"[LLM] Async rate limited ({resp.status}), retrying in {wait:.1f}s...")
                            await asyncio.sleep(wait)
                            continue
                        else:
                            body = await resp.text()
                            raise Exception(f"HTTP {resp.status}: {body[:200]}")
                except aiohttp.ClientError as e:
                    last_error = e
                    if attempt < _MAX_RETRIES - 1:
                        wait = exponential_backoff(attempt)
                        logger.warning(f"[LLM] Async client error, retrying in {wait:.1f}s: {e}")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"[LLM] Async all retries exhausted: {e}")
                except Exception as e:
                    if e is not last_error:
                        last_error = e
                    if attempt < _MAX_RETRIES - 1:
                        wait = exponential_backoff(attempt)
                        logger.warning(f"[LLM] Async non-client error, retrying in {wait:.1f}s: {e}")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"[LLM] Async non-client error, all retries exhausted: {e}")

        self._available = False
        if last_error is None:
            last_error = Exception("All async retry attempts failed with no specific error")
        raise last_error

    def _make_fallback_response(self, fallback_text: str) -> Dict[str, Any]:
        return {
            "choices": [{
                "message": {"content": fallback_text, "role": "assistant"},
                "finish_reason": "stop"
            }],
            "model": "fallback",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

    def get_response_text(self, response: Dict[str, Any]) -> str:
        try:
            choices = response.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
        except Exception as e:
            logger.error(f"Failed to extract response text: {e}")
            return ""

    def reset_stats(self):
        self._total_tokens = 0
        self._total_cost = 0.0

    def complete_json(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        schema: Any = None,
        fallback: Any = None,
        agent_name: str = "unknown",
    ) -> Any:
        """
        发送LLM请求并解析JSON响应，失败时返回fallback。
        封装了重试、JSON提取、schema验证和降级逻辑。
        """
        from app.core.llm_utils import extract_json_from_llm_response

        if not self.is_available:
            logger.info(f"[{agent_name}] LLM unavailable, using fallback")
            return fallback

        try:
            response = self.complete(
                messages=messages, temperature=temperature, max_tokens=max_tokens
            )
            text = self.get_response_text(response)
            if not text:
                logger.warning(f"[{agent_name}] LLM returned empty response")
                return fallback
            result = extract_json_from_llm_response(text, schema=schema, fallback=fallback)
            if result is fallback:
                logger.warning(f"[{agent_name}] JSON extraction returned fallback")
            return result
        except Exception as e:
            logger.warning(f"[{agent_name}] LLM call failed: {e}, using fallback")
            return fallback


_llm_client: Optional[LLMClient] = None
_llm_client_lock = threading.Lock()


def get_llm_client() -> LLMClient:
    """获取LLM客户端实例（线程安全单例）"""
    global _llm_client
    if _llm_client is None:
        with _llm_client_lock:
            if _llm_client is None:
                _llm_client = LLMClient()
    return _llm_client


def create_llm_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: float = 120.0
) -> LLMClient:
    """创建新的LLM客户端实例（用于隔离场景）"""
    return LLMClient(
        model=model,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )


def test_llm_connection() -> Dict[str, Any]:
    """测试LLM连接"""
    client = get_llm_client()

    try:
        response = client.complete([
            {"role": "user", "content": "Hello, respond with just 'OK'"}
        ])

        text = client.get_response_text(response)
        success = "ok" in text.strip().lower()

        return {
            "success": success,
            "model": client.model,
            "response": text,
            "total_tokens": client.total_tokens,
            "total_cost": client.total_cost,
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "model": client.model,
            "response": None,
            "total_tokens": client.total_tokens,
            "total_cost": client.total_cost,
            "error": str(e)
        }