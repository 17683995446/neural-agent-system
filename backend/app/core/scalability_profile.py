"""
ScalabilityProfile — 按项目规模自动配置参数
SMALL: <=20 files
MEDIUM: <=200 files
LARGE: <=2000 files
XLARGE: >2000 files
"""
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class ScalabilityProfile:
    SMALL: Dict = {
        "max_agents": 50,
        "max_output_items": 30,
        "max_modifications": 30,
        "max_function_details": 30,
        "enable_module_partition": False,
        "enable_incremental": True,
        "enable_response_cache": False,
        "llm_max_qps": 5.0,
        "llm_max_concurrent": 3,
        "context_max_chars": 4000,
    }

    MEDIUM: Dict = {
        "max_agents_per_module": 50,
        "max_total_agents": 200,
        "max_module_summaries": 50,
        "max_file_summaries": 100,
        "max_function_details": 30,
        "max_modifications": 50,
        "enable_module_partition": True,
        "enable_incremental": True,
        "enable_response_cache": True,
        "llm_max_qps": 3.0,
        "llm_max_concurrent": 3,
        "context_max_chars": 6000,
    }

    LARGE: Dict = {
        "max_agents_per_module": 100,
        "max_total_agents": 500,
        "max_module_summaries": 100,
        "max_file_summaries": 200,
        "max_function_details": 50,
        "max_modifications": 100,
        "enable_module_partition": True,
        "enable_incremental": True,
        "enable_response_cache": True,
        "llm_max_qps": 3.0,
        "llm_max_concurrent": 5,
        "context_max_chars": 8000,
    }

    XLARGE: Dict = {
        "max_agents_per_module": 200,
        "max_total_agents": 1000,
        "max_module_summaries": 200,
        "max_file_summaries": 500,
        "max_function_details": 100,
        "max_modifications": 200,
        "enable_module_partition": True,
        "enable_incremental": True,
        "enable_response_cache": True,
        "enable_ast_cache": True,
        "enable_circuit_breaker": True,
        "llm_max_qps": 2.0,
        "llm_max_concurrent": 3,
        "context_max_chars": 10000,
    }

    CHEAP_LLM: Dict = {
        "max_agents_per_module": 9999,
        "max_total_agents": 9999,
        "max_module_summaries": 9999,
        "max_file_summaries": 9999,
        "max_function_details": 9999,
        "max_modifications": 9999,
        "enable_module_partition": True,
        "enable_incremental": True,
        "enable_response_cache": True,
        "enable_ast_cache": True,
        "enable_circuit_breaker": False,
        "enable_agent_pool": True,
        "enable_cheap_llm": True,
        "llm_max_qps": 999.0,
        "llm_max_concurrent": 999,
        "context_max_chars": 4000,
        "cheap_llm_max_tokens": 1024,
        "agent_pool_workers": 0,
    }

    _CODE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c"}
    _EXCLUDED = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

    @classmethod
    def detect(cls, code_repo_path: str) -> Dict:
        root = Path(code_repo_path)
        file_count = 0
        total_lines = 0

        for ext in cls._CODE_EXTENSIONS:
            for f in root.rglob(f"*{ext}"):
                if f.is_file() and not any(x in str(f) for x in cls._EXCLUDED):
                    file_count += 1
                    try:
                        with f.open(encoding="utf-8", errors="replace") as fh:
                            total_lines += sum(1 for _ in fh)
                    except Exception:
                        pass

        from app.core.config import settings
        if getattr(settings, "cheap_llm_mode", False):
            profile = "CHEAP_LLM"
            config = cls.CHEAP_LLM
        elif file_count <= 20:
            profile = "SMALL"
            config = cls.SMALL
        elif file_count <= 200:
            profile = "MEDIUM"
            config = cls.MEDIUM
        elif file_count <= 2000:
            profile = "LARGE"
            config = cls.LARGE
        else:
            profile = "XLARGE"
            config = cls.XLARGE

        logger.info(
            "Project: %d files, %d lines → %s profile",
            file_count, total_lines, profile,
        )
        return {
            **config,
            "_profile": profile,
            "_file_count": file_count,
            "_total_lines": total_lines,
        }
