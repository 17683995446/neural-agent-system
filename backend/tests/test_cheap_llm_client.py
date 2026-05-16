"""
核心基础模块单元测试 — CheapLLMClient
覆盖: 初始化/可用性/URL构建/统计
"""
import pytest
from unittest.mock import MagicMock, patch

from app.core.cheap_llm_client import CheapLLMClient


class TestCheapLLMInit:
    def test_default_init(self):
        client = CheapLLMClient(api_key="test_key", api_base="http://localhost:8000")
        assert client.api_key == "test_key"
        assert client.max_tokens == 2048
        assert client.temperature == 0.3

    def test_custom_params(self):
        client = CheapLLMClient(
            model="my-model",
            api_key="k",
            api_base="http://api.test",
            max_tokens=512,
            temperature=0.5,
        )
        assert client.model == "my-model"
        assert client.max_tokens == 512
        assert client.temperature == 0.5


class TestCheapLLMAvailability:
    def test_available_with_key(self):
        client = CheapLLMClient(api_key="valid_key", api_base="http://localhost")
        assert client.is_available

    def test_unavailable_without_key(self):
        with patch("app.core.cheap_llm_client.settings") as mock_settings:
            mock_settings.anthropic_auth_token = None
            mock_settings.openai_api_key = None
            client = CheapLLMClient(api_key=None, api_base="http://localhost")
            assert not client.is_available


class TestCheapLLMBuildUrl:
    def test_plain_base(self):
        client = CheapLLMClient(api_key="k", api_base="http://api.test")
        url = client._build_url()
        assert url == "http://api.test/v1/chat/completions"

    def test_base_with_v1(self):
        client = CheapLLMClient(api_key="k", api_base="http://api.test/v1")
        url = client._build_url()
        assert url == "http://api.test/v1/chat/completions"

    def test_base_already_complete(self):
        client = CheapLLMClient(api_key="k", api_base="http://api.test/v1/chat/completions")
        url = client._build_url()
        assert url == "http://api.test/v1/chat/completions"


class TestCheapLLMGetResponseText:
    def test_normal_response(self):
        client = CheapLLMClient(api_key="k", api_base="http://localhost")
        resp = {"choices": [{"message": {"content": "hello"}}]}
        assert client.get_response_text(resp) == "hello"

    def test_none_response(self):
        client = CheapLLMClient(api_key="k", api_base="http://localhost")
        assert client.get_response_text(None) == ""

    def test_empty_choices(self):
        client = CheapLLMClient(api_key="k", api_base="http://localhost")
        assert client.get_response_text({"choices": []}) == ""

    def test_reasoning_fallback(self):
        client = CheapLLMClient(api_key="k", api_base="http://localhost")
        resp = {"choices": [{"message": {"reasoning": "think step", "content": ""}}]}
        assert client.get_response_text(resp) == "think step"


class TestCheapLLMStats:
    def test_initial_stats(self):
        client = CheapLLMClient(api_key="k", api_base="http://localhost")
        stats = client.get_stats()
        assert stats["total_calls"] == 0
        assert stats["total_errors"] == 0
        assert stats["error_rate"] == 0.0

    def test_unavailable_returns_none(self):
        with patch("app.core.cheap_llm_client.settings") as mock_settings:
            mock_settings.anthropic_auth_token = None
            mock_settings.openai_api_key = None
            mock_settings.default_llm_model = "x"
            mock_settings.anthropic_base_url = "http://localhost"
            client = CheapLLMClient(api_key=None, api_base="http://localhost")
            result = client.complete([{"role": "user", "content": "hi"}])
            assert result is None
