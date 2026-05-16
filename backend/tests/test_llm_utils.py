"""
核心基础模块单元测试 — LLM工具函数 (llm_utils)
覆盖: extract_json_from_llm_response, extract_code_from_llm_response, truncate_code
场景: 正常/边界/异常
"""
import pytest
from typing import Optional
from pydantic import BaseModel

from app.core.llm_utils import (
    extract_json_from_llm_response,
    extract_code_from_llm_response,
    truncate_code,
)


class MySchema(BaseModel):
    name: str
    value: int


class TestExtractJson:
    def test_pure_json(self):
        text = '{"name": "test", "value": 42}'
        result = extract_json_from_llm_response(text)
        assert result == {"name": "test", "value": 42}

    def test_json_in_code_block(self):
        text = '```json\n{"name": "test", "value": 42}\n```'
        result = extract_json_from_llm_response(text)
        assert result == {"name": "test", "value": 42}

    def test_json_in_plain_code_block(self):
        text = '```\n{"name": "test", "value": 42}\n```'
        result = extract_json_from_llm_response(text)
        assert result == {"name": "test", "value": 42}

    def test_json_with_prefix_text(self):
        text = 'Here is the result:\n{"name": "test", "value": 42}'
        result = extract_json_from_llm_response(text)
        assert result == {"name": "test", "value": 42}

    def test_json_with_suffix_text(self):
        text = '{"name": "test", "value": 42}\nDone.'
        result = extract_json_from_llm_response(text)
        assert result == {"name": "test", "value": 42}

    def test_json_array(self):
        text = '[1, 2, 3]'
        result = extract_json_from_llm_response(text)
        assert result == [1, 2, 3]

    def test_nested_json(self):
        text = '{"a": {"b": [1, 2]}, "c": null}'
        result = extract_json_from_llm_response(text)
        assert result == {"a": {"b": [1, 2]}, "c": None}

    def test_empty_string_returns_fallback(self):
        assert extract_json_from_llm_response("", fallback="fb") == "fb"

    def test_whitespace_only_returns_fallback(self):
        assert extract_json_from_llm_response("   \n  ", fallback="fb") == "fb"

    def test_invalid_json_returns_fallback(self):
        assert extract_json_from_llm_response("not json at all", fallback="fb") == "fb"

    def test_with_schema_valid(self):
        text = '{"name": "test", "value": 42}'
        result = extract_json_from_llm_response(text, schema=MySchema, fallback=None)
        assert result == {"name": "test", "value": 42}

    def test_with_schema_invalid_returns_fallback(self):
        text = '{"name": "test", "value": "not_int"}'
        result = extract_json_from_llm_response(text, schema=MySchema, fallback="fb")
        assert result == "fb"

    def test_with_schema_missing_field_returns_fallback(self):
        text = '{"name": "test"}'
        result = extract_json_from_llm_response(text, schema=MySchema, fallback="fb")
        assert result == "fb"

    def test_chinese_json(self):
        text = '{"名称": "测试", "值": 42}'
        result = extract_json_from_llm_response(text)
        assert result == {"名称": "测试", "值": 42}

    def test_boolean_json(self):
        text = '{"flag": true, "disabled": false}'
        result = extract_json_from_llm_response(text)
        assert result == {"flag": True, "disabled": False}


class TestExtractCode:
    def test_python_code_block(self):
        text = '```python\ndef hello():\n    return "hi"\n```'
        result = extract_code_from_llm_response(text, language="python")
        assert result == 'def hello():\n    return "hi"'

    def test_plain_code_block(self):
        text = '```\nprint("hello")\n```'
        result = extract_code_from_llm_response(text)
        assert result == 'print("hello")'

    def test_no_code_block_returns_text(self):
        text = 'def hello():\n    pass'
        result = extract_code_from_llm_response(text)
        assert result == text

    def test_empty_string(self):
        assert extract_code_from_llm_response("") is None

    def test_whitespace_only(self):
        assert extract_code_from_llm_response("   ") is None

    def test_specific_language_filter(self):
        text = '```javascript\nconsole.log("hi")\n```\n```python\nprint("hi")\n```'
        result = extract_code_from_llm_response(text, language="python")
        assert 'print("hi")' in result

    def test_code_with_surrounding_text(self):
        text = 'Here is the code:\n```python\nx = 1\n```\nEnd.'
        result = extract_code_from_llm_response(text, language="python")
        assert result == "x = 1"


class TestTruncateCode:
    def test_short_code_unchanged(self):
        code = "def hello():\n    return 1"
        assert truncate_code(code) == code

    def test_empty_string(self):
        assert truncate_code("") == ""

    def test_truncate_by_chars(self):
        code = "x" * 10000
        result = truncate_code(code, max_chars=8000, max_lines=99999)
        assert len(result) < len(code)
        assert "truncated" in result

    def test_truncate_by_lines(self):
        lines = [f"line_{i}" for i in range(300)]
        code = "\n".join(lines)
        result = truncate_code(code, max_chars=999999, max_lines=200)
        assert "truncated" in result
        assert len(result.split("\n")) < 300

    def test_preserves_head_and_tail(self):
        lines = [f"line_{i}" for i in range(300)]
        code = "\n".join(lines)
        result = truncate_code(code, max_chars=999999, max_lines=200)
        assert "line_0" in result
        assert "line_299" in result
