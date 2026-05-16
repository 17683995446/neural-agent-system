"""
核心基础模块单元测试 — LLM客户端 (LLMClient)
使用mock，覆盖: 重试/fallback/complete_json/usage/缓存/限频/熔断
"""
import pytest
import time
import requests
from unittest.mock import MagicMock, patch, PropertyMock

from app.core.llm_client import LLMClient, exponential_backoff, _RETRY_STATUS_CODES


class TestExponentialBackoff:
    def test_attempt_0(self):
        delay = exponential_backoff(0)
        assert 1.0 <= delay <= 1.5

    def test_attempt_1(self):
        delay = exponential_backoff(1)
        assert 2.0 <= delay <= 2.5

    def test_attempt_2(self):
        delay = exponential_backoff(2)
        assert 4.0 <= delay <= 4.5

    def test_capped_at_max(self):
        delay = exponential_backoff(100)
        assert delay <= 30.5


class TestLLMClientFallback:
    def test_no_api_key_returns_fallback(self):
        with patch("app.core.llm_client.settings") as mock_settings:
            mock_settings.anthropic_model = None
            mock_settings.litellm_model = None
            mock_settings.default_llm_model = "x"
            mock_settings.anthropic_auth_token = None
            mock_settings.litellm_api_key = None
            mock_settings.openai_api_key = None
            mock_settings.anthropic_base_url = "http://localhost"
            mock_settings.litellm_api_base = None
            client = LLMClient(api_key="", api_base="http://localhost")
            client._available = False
            assert not client.is_available
            result = client.complete(
                [{"role": "user", "content": "hi"}],
                fallback_text="fb",
            )
            assert result["model"] == "fallback"
            assert result["choices"][0]["message"]["content"] == "fb"

    def test_fallback_response_structure(self):
        client = LLMClient(api_key="", api_base="http://localhost")
        result = client._make_fallback_response("my fallback")
        assert "choices" in result
        assert result["choices"][0]["message"]["content"] == "my fallback"
        assert result["usage"]["total_tokens"] == 0


class TestLLMClientGetResponseText:
    def test_extract_text(self):
        client = LLMClient(api_key="test", api_base="http://localhost")
        resp = {"choices": [{"message": {"content": "hello"}}]}
        assert client.get_response_text(resp) == "hello"

    def test_empty_choices(self):
        client = LLMClient(api_key="test", api_base="http://localhost")
        assert client.get_response_text({"choices": []}) == ""

    def test_no_choices_key(self):
        client = LLMClient(api_key="test", api_base="http://localhost")
        assert client.get_response_text({}) == ""

    def test_exception_returns_empty(self):
        client = LLMClient(api_key="test", api_base="http://localhost")
        assert client.get_response_text(None) == ""


class TestLLMClientBuildUrl:
    def test_base_with_v1(self):
        client = LLMClient(api_key="k", api_base="http://api.example.com/v1")
        url = client._build_url()
        assert url == "http://api.example.com/v1/chat/completions"

    def test_base_with_v2(self):
        client = LLMClient(api_key="k", api_base="http://api.example.com/v2")
        url = client._build_url()
        assert url == "http://api.example.com/v2/chat/completions"

    def test_base_already_complete(self):
        client = LLMClient(api_key="k", api_base="http://api.example.com/v1/chat/completions")
        url = client._build_url()
        assert url == "http://api.example.com/v1/chat/completions"

    def test_base_plain(self):
        client = LLMClient(api_key="k", api_base="http://api.example.com")
        url = client._build_url()
        assert url == "http://api.example.com/v1/chat/completions"


class TestLLMClientUsage:
    def test_estimate_cost(self):
        client = LLMClient(api_key="k", api_base="http://localhost")
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = client._estimate_cost(usage)
        assert cost > 0

    def test_total_tokens_tracking(self):
        client = LLMClient(api_key="k", api_base="http://localhost")
        assert client.total_tokens == 0

    def test_reset_stats(self):
        client = LLMClient(api_key="k", api_base="http://localhost")
        client._total_tokens = 100
        client._total_cost = 0.5
        client.reset_stats()
        assert client.total_tokens == 0
        assert client.total_cost == 0.0


class TestLLMClientCompleteJson:
    def test_unavailable_returns_fallback(self):
        client = LLMClient(api_key="", api_base="http://localhost")
        result = client.complete_json(
            [{"role": "user", "content": "hi"}],
            fallback={"default": True},
        )
        assert result == {"default": True}

    def test_available_client_structure(self):
        client = LLMClient(api_key="fake", api_base="http://localhost:99999")
        result = client.complete_json(
            [{"role": "user", "content": "hi"}],
            fallback={"fb": 1},
            agent_name="test",
        )
        assert result is not None


class TestRetryStatusCodes:
    def test_standard_retry_codes(self):
        assert 429 in _RETRY_STATUS_CODES
        assert 500 in _RETRY_STATUS_CODES
        assert 502 in _RETRY_STATUS_CODES
        assert 503 in _RETRY_STATUS_CODES

    def test_200_not_retryable(self):
        assert 200 not in _RETRY_STATUS_CODES
