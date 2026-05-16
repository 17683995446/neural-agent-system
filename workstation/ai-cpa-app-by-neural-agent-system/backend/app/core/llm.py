import asyncio
import importlib
import sys
from typing import Optional

from app.core.config import settings

_neural_path = "D:/claude_workspace/neural-agent-system/backend"
_client = None


def _get_client():
    global _client
    if _client is None:
        if _neural_path not in sys.path:
            sys.path.insert(0, _neural_path)
        existing_app = sys.modules.get("app")
        existing_config = sys.modules.get("app.core.config")
        existing_core = sys.modules.get("app.core")
        try:
            sys.modules.pop("app.core.config", None)
            sys.modules.pop("app.core", None)
            sys.modules.pop("app", None)
            from app.core.cheap_llm_client import CheapLLMClient as _Client
        finally:
            if existing_app is not None:
                sys.modules["app"] = existing_app
            if existing_core is not None:
                sys.modules["app.core"] = existing_core
            if existing_config is not None:
                sys.modules["app.core.config"] = existing_config
            _cpa_app_path = "D:/claude_workspace/neural-agent-system/workstation/ai-cpa-app-by-neural-agent-system/backend"
            if _cpa_app_path not in sys.path:
                sys.path.insert(0, _cpa_app_path)
        _client = _Client(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE,
            max_tokens=2048,
            temperature=0.3,
        )
    return _client


async def llm_generate(prompt: str, max_tokens: int = 2048, temperature: float = 0.3) -> str:
    client = _get_client()
    messages = [{"role": "user", "content": prompt}]
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.complete(messages, max_tokens=max_tokens, temperature=temperature),
    )
    return client.get_response_text(response)


async def llm_chat(messages: list, max_tokens: int = 2048, temperature: float = 0.3) -> str:
    client = _get_client()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.complete(messages, max_tokens=max_tokens, temperature=temperature),
    )
    return client.get_response_text(response)
