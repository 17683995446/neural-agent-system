"""
LLM工具函数 - 统一JSON提取、代码截断等
"""
import json
import re
import logging
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def extract_json_from_llm_response(
    text: str,
    schema: Optional[Type[BaseModel]] = None,
    fallback: Any = None,
) -> Any:
    """
    从LLM响应中提取JSON，支持多种格式：
    1. ```json ... ``` 代码块
    2. ``` ... ``` 代码块
    3. 裸JSON字符串
    """
    if not text or not text.strip():
        return fallback

    text = text.strip()
    json_str = None

    code_block_pattern = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.DOTALL)
    match = code_block_pattern.search(text)
    if match:
        json_str = match.group(1).strip()

    if json_str is None:
        cleaned = re.sub(r'^[^{\[]*', '', text)
        cleaned = re.sub(r'[^}\]]*$', '', cleaned)
        if cleaned:
            json_str = cleaned

    if json_str is None:
        json_str = text

    try:
        result = json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"JSON parse failed: {e}, text preview: {text[:100]}")
        return fallback

    if schema is not None:
        try:
            validated = schema.model_validate(result)
            return validated.model_dump()
        except ValidationError as e:
            logger.warning(f"Schema validation failed: {e}")
            return fallback

    return result


def extract_code_from_llm_response(text: str, language: str = "") -> Optional[str]:
    """
    从LLM响应中提取代码块
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    lang_pattern = re.escape(language) if language else r'\w*'
    pattern = re.compile(rf'```(?:{lang_pattern})\s*\n(.*?)\n```', re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()

    pattern = re.compile(r'```\s*\n(.*?)\n```', re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()

    return text.strip()


def truncate_code(content: str, max_chars: int = 8000, max_lines: int = 200) -> str:
    """截断过长代码，保留头部和尾部"""
    if not content:
        return content
    lines = content.split('\n')
    if len(lines) > max_lines:
        head = '\n'.join(lines[:max_lines // 2])
        tail = '\n'.join(lines[-(max_lines // 2):])
        return f"{head}\n# ... (truncated {len(lines) - max_lines} lines) ...\n{tail}"
    if len(content) > max_chars:
        return content[:max_chars] + f"\n# ... (truncated, total {len(content)} chars) ..."
    return content
