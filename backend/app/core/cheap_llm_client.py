"""
CheapLLMClient — 极便宜LLM专用客户端
特点:
- 无限频(便宜API不需要限频)
- 超轻退避(仅重试1次, 间隔0.5s)
- 超短超时(连接3s, 读取30s)
- 低max_tokens(1024, 便宜模型输出短即可)
- 每个agent独立client(无共享状态)
- 自动降级: 返回空而非抛异常
"""
import time
import random
from typing import Any, Dict, List, Optional

import requests

from app.core.config import settings


class CheapLLMClient:
    """
    极便宜LLM客户端 — 用于海量agent并行调用

    设计原则:
    1. 不限频 — 便宜API允许大量调用
    2. 快失败 — 只重试1次, 不浪费时间
    3. 每请求独立 — 无共享状态, 线程安全
    4. 零传播 — 失败返回None, 不抛异常给上层
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ):
        self.model = model or settings.cheap_llm_model or settings.default_llm_model
        self.api_key = (
            api_key
            or settings.anthropic_auth_token
            or settings.openai_api_key
        )
        self.api_base = api_base or settings.anthropic_base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._total_calls = 0
        self._total_errors = 0

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def _build_url(self) -> str:
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        import re
        if re.search(r"/v\d+$", base):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def complete(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        单次调用 — 只重试1次, 失败返回None

        与LLMClient.complete()的区别:
        - 无限频/熔断/缓存
        - 无重试循环(最多1次重试)
        - 返回None而非raise
        """
        if not self.is_available:
            return None

        for attempt in range(2):
            self._total_calls += 1
            try:
                url = self._build_url()
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", self.temperature),
                    "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                }
                resp = requests.post(
                    url, headers=headers, json=payload, timeout=(3, 30)
                )
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in {403, 429, 500, 502, 503, 529}:
                    wait = 1.0 * (2 ** attempt) + random.uniform(0, 0.5)
                    time.sleep(wait)
                    continue
                return None
            except requests.exceptions.RequestException:
                if attempt == 0:
                    time.sleep(0.3)
                    continue
                self._total_errors += 1
                return None
            except Exception:
                self._total_errors += 1
                return None

        self._total_errors += 1
        return None

    def get_response_text(self, response: Optional[Dict[str, Any]]) -> str:
        if response is None:
            return ""
        try:
            choices = response.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                if content:
                    return content
                reasoning = msg.get("reasoning", "")
                if reasoning:
                    return reasoning
        except Exception:
            pass
        return ""

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "error_rate": self._total_errors / max(self._total_calls, 1),
        }
