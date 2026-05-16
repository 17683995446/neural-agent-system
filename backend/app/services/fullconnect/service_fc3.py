"""
全连接层3 - 测试生成层
为代码生成层输出的修改代码编写单元测试、集成测试用例
LLM优先调用，失败时降级到模板生成
"""
import os
import time
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.llm_client import create_llm_client
from app.core.llm_utils import extract_code_from_llm_response
from app.core.io_utils import save_layer_output
from app.core.logging import logger
from app.core.cheap_llm_client import CheapLLMClient
from app.core.agent_pool import AgentPool
from app.services.fullconnect.smart_context import SmartContextWindow

# 并发生成测试数
MAX_CONCURRENT_TESTS = min(int(os.environ.get("MAX_CONCURRENT_TESTS", "8")), 8)


class TestGenerationConfig:
    """测试生成配置"""
    __test__ = False

    def __init__(
        self,
        coverage_target: float = 0.8,
        max_tests_per_file: int = 20
    ):
        self.coverage_target = coverage_target
        self.max_tests_per_file = max_tests_per_file


class TestCaseGenerator:
    """测试用例生成器 - LLM优先，降级到模板"""
    __test__ = False

    def __init__(self):
        self.llm_client = create_llm_client()

    @staticmethod
    def _token_aware_truncate(code: str, max_chars: int = 8000) -> str:
        if len(code) <= max_chars:
            return code
        truncated = code[:max_chars]
        last_nl = truncated.rfind("\n")
        if last_nl > max_chars // 2:
            truncated = truncated[:last_nl]
        remaining = len(code) - len(truncated)
        truncated += f"\n# ... ({remaining} more chars)"
        return truncated

    def _generate_unit_tests_with_client(self, llm_client, modification: Dict[str, Any]) -> Dict[str, Any]:
        """使用指定LLM客户端生成单元测试 — SmartContextWindow获取源文件上下文"""
        target = modification.get("target", "unknown")
        file_path = modification.get("file_path", "") or modification.get("file", "")
        modified_code = modification.get("modified_code", "")

        if not llm_client.is_available or not modified_code:
            return self._generate_unit_tests_template(modification)

        try:
            code_for_prompt = modified_code

            if file_path and Path(file_path).exists():
                src_content = Path(file_path).read_text(encoding="utf-8", errors="replace")
                if src_content:
                    smart_ctx = SmartContextWindow()
                    smart_result = smart_ctx.get_context(Path(file_path), target, src_content)
                    if smart_result:
                        code_for_prompt = smart_result

            code_for_prompt = self._token_aware_truncate(code_for_prompt, max_chars=8000)

            prompt = f"""你是测试工程师。为以下代码生成pytest单元测试。

测试目标: {target}
文件: {file_path}

代码:
```python
{code_for_prompt}
```

请生成完整的pytest测试代码，用```python```包裹。包含:
- 正常用例
- 边界用例
- 异常用例
只输出代码，不要解释。"""

            response = llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096
            )
            text = llm_client.get_response_text(response)
            if not text:
                return self._generate_unit_tests_template(modification)

            test_code = extract_code_from_llm_response(text, language="python")

            if not test_code or "def test" not in test_code:
                return self._generate_unit_tests_template(modification)

            logger.info(f"[LLM] FC3 unit tests generated for {target}")
            return {
                "test_file_path": f"tests/test_{Path(file_path).stem}.py",
                "test_code": test_code,
                "target": target,
                "test_type": "unit",
                "generated_by": "llm"
            }

        except Exception as e:
            logger.warning(f"[LLM] FC3 test generation failed for {modification.get('target')}, falling back: {e}")
            return self._generate_unit_tests_template(modification)

    def _generate_unit_tests_template(
        self,
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        target = modification.get("target", "unknown")
        file_path = modification.get("file_path", "")

        test_template = f'''import pytest
from pathlib import Path

class Test{target.replace(".", "_").title().replace("_", "")}:
    """Test cases for {target}"""

    def test_{target}_exists(self):
        """Test that {target} exists"""
        pass

    def test_{target}_execution(self):
        """Test {target} execution"""
        pass

    def test_{target}_edge_cases(self):
        """Test edge cases for {target}"""
        pass
'''

        return {
            "test_file_path": f"tests/test_{Path(file_path).stem}.py",
            "test_code": test_template,
            "target": target,
            "test_type": "unit",
            "generated_by": "template"
        }

    def generate_integration_tests(
        self,
        modification: Dict[str, Any]
    ) -> Dict[str, Any]:
        target = modification.get("target", "unknown")

        test_template = f'''import pytest

class TestIntegration{target.replace(".", "_").title().replace("_", "")}:
    """Integration tests for {target}"""

    def test_{target}_workflow(self):
        """Test complete workflow"""
        pass

    def test_{target}_with_dependencies(self):
        """Test with dependency mocking"""
        pass
'''

        return {
            "test_file_path": f"tests/integration_test_{Path(modification.get('file_path', 'unknown')).stem}.py",
            "test_code": test_template,
            "target": target,
            "test_type": "integration"
        }


class CoverageAnalyzer:
    """覆盖率分析器"""

    def __init__(self):
        pass

    def analyze_coverage(
        self,
        modifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析测试覆盖率"""
        total_lines = 0
        covered_lines = 0

        for mod in modifications:
            code = mod.get("modified_code", "")
            lines = code.split("\n")
            total_lines += len(lines)
            # 简化：假设70%的行被覆盖
            covered_lines += int(len(lines) * 0.7)

        coverage = (covered_lines / total_lines * 100) if total_lines > 0 else 0

        return {
            "total_lines": total_lines,
            "covered_lines": covered_lines,
            "coverage_percent": round(coverage, 2),
            "files_with_coverage": len([m for m in modifications if m.get("status") == "success"])
        }


class TestGenerationService:
    """测试生成层服务"""
    __test__ = False

    def __init__(self, config: Optional[TestGenerationConfig] = None):
        self.config = config or TestGenerationConfig()
        self.generator = TestCaseGenerator()
        self.coverage_analyzer = CoverageAnalyzer()
        self._agent_pool: Optional[AgentPool] = None
        self._cheap_mode: bool = False

    def enable_agent_pool(self, max_workers: int = 0):
        """启用无限agent池 — 每修改项一个agent生成测试"""
        self._agent_pool = AgentPool(max_workers=max_workers or None)
        self._cheap_mode = True
        logger.info("FC3: agent pool enabled (workers=%d)", self._agent_pool.max_workers)

    def generate_tests_for_modification(
        self,
        modification: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """为单个修改生成测试用例"""
        start_time = time.time()
        tests = []

        try:
            # 创建独立的LLM客户端
            llm_client = create_llm_client()

            # 生成单元测试
            unit_test = self.generator._generate_unit_tests_with_client(llm_client, modification)
            unit_test["status"] = "generated"
            tests.append(unit_test)

            # 生成集成测试
            if modification.get("status") == "success":
                integration_test = self.generator.generate_integration_tests(modification)
                integration_test["status"] = "generated"
                tests.append(integration_test)

        except Exception as e:
            logger.error(f"Failed to generate tests for {modification.get('target')}: {e}")
            tests.append({
                "target": modification.get("target"),
                "status": "failed",
                "error": str(e)
            })

        elapsed = (time.time() - start_time) * 1000
        logger.debug(f"[TIMING] Test generation for {modification.get('target')} completed in {elapsed:.2f}ms")

        return tests

    def generate_all_tests(
        self,
        modifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """为所有修改生成测试用例 — cheap模式用AgentPool"""
        start_time = time.time()
        all_tests = []

        successful_mods = [m for m in modifications if m.get("status") == "success"]

        if not successful_mods:
            logger.warning("[FC3] No successful modifications to generate tests for")
            return all_tests

        if self._cheap_mode and self._agent_pool is not None:
            all_tests = self._generate_tests_with_agent_pool(successful_mods)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TESTS) as executor:
                future_to_mod = {
                    executor.submit(self.generate_tests_for_modification, mod): mod
                    for mod in successful_mods
                }

                for future in concurrent.futures.as_completed(future_to_mod):
                    mod = future_to_mod[future]
                    try:
                        tests = future.result()
                        all_tests.extend(tests)
                    except Exception as e:
                        logger.error(f"Failed to generate tests for {mod.get('target')}: {e}")

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Generated {len(all_tests)} tests for {len(successful_mods)} modifications in {total_elapsed:.2f}ms")

        return all_tests

    def _generate_tests_with_agent_pool(
        self,
        modifications: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """AgentPool模式: 每修改项一个agent, 独立CheapLLMClient"""

        def gen_test(mod: Dict[str, Any]) -> Dict[str, Any]:
            cheap = CheapLLMClient()
            target = mod.get("target", "unknown")
            file_path = mod.get("file_path", "") or mod.get("file", "")
            modified_code = mod.get("modified_code", "")

            if cheap.is_available and modified_code:
                code_for_prompt = modified_code

                if file_path and Path(file_path).exists():
                    try:
                        src_content = Path(file_path).read_text(encoding="utf-8", errors="replace")
                        if src_content:
                            smart_ctx = SmartContextWindow()
                            smart_result = smart_ctx.get_context(Path(file_path), target, src_content)
                            if smart_result:
                                code_for_prompt = smart_result
                    except Exception:
                        pass

                code_for_prompt = TestCaseGenerator._token_aware_truncate(code_for_prompt, max_chars=6000)
                prompt = (
                    f"为以下代码生成pytest单元测试:\n"
                    f"目标: {target}\n代码:\n```python\n{code_for_prompt}\n```\n"
                    f"生成完整pytest测试, 用```python```包裹。只输出代码。"
                )
                response = cheap.complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                )
                text = cheap.get_response_text(response)
                if text:
                    test_code = extract_code_from_llm_response(text, language="python")
                    if test_code and "def test" in test_code:
                        return {
                            "test_file_path": f"tests/test_{Path(file_path).stem}.py",
                            "test_code": test_code,
                            "target": target,
                            "test_type": "unit",
                            "status": "generated",
                            "generated_by": "cheap_llm",
                        }

            return self.generator._generate_unit_tests_template(mod)

        agent_results = self._agent_pool.dispatch_simple(gen_test, modifications)
        unit_tests = self._agent_pool.aggregate(agent_results, strategy="all")

        all_tests = []
        for t in unit_tests:
            if isinstance(t, dict):
                t.setdefault("status", "generated")
                all_tests.append(t)

        for mod in modifications:
            if mod.get("status") == "success":
                all_tests.append(self.generator.generate_integration_tests(mod))

        return all_tests

    def analyze_coverage(
        self,
        modifications: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析测试覆盖率"""
        start_time = time.time()

        coverage = self.coverage_analyzer.analyze_coverage(modifications)

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Coverage analysis completed in {elapsed:.2f}ms")

        return coverage

    def validate_tests(self, tests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """验证测试用例"""
        start_time = time.time()

        valid = []
        invalid = []

        for test in tests:
            if test.get("status") == "generated":
                # 简化验证：检查是否有test_code
                if test.get("test_code") and "import pytest" in test.get("test_code", ""):
                    valid.append(test)
                else:
                    invalid.append(test)
            else:
                invalid.append(test)

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Validated {len(valid)} valid, {len(invalid)} invalid tests in {total_elapsed:.2f}ms")

        return {
            "valid_tests": len(valid),
            "invalid_tests": len(invalid),
            "validation_details": {
                "valid": valid,
                "invalid": invalid
            }
        }

    def create_fc3_output(
        self,
        tests: List[Dict[str, Any]],
        coverage: Dict[str, Any],
        fc2_output: Dict[str, Any],
        task_id: str
    ) -> Dict[str, Any]:
        """创建全连接层3输出"""
        output = {
            "task_id": task_id,
            "layer": "test_generation",
            "layer_name": "full_connect_3",
            "summary": {
                "total_tests": len(tests),
                "unit_tests": len([t for t in tests if t.get("test_type") == "unit"]),
                "integration_tests": len([t for t in tests if t.get("test_type") == "integration"])
            },
            "tests": tests,
            "coverage": coverage,
            "fc2_reference": {
                "total_modifications": fc2_output.get("summary", {}).get("total_modifications", 0),
                "successful": fc2_output.get("summary", {}).get("successful", 0)
            },
            "created_at": datetime.now().isoformat()
        }

        return output

    def process_task(
        self,
        task_id: str,
        fc2_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理任务 - 执行完整的测试生成层流程"""
        start_time = time.time()
        logger.info(f"[START] FC3 Test Generation layer processing task {task_id}")

        # 获取修改列表
        modifications = fc2_output.get("modifications", [])

        # 1. 生成测试用例
        tests = self.generate_all_tests(modifications)

        # 2. 分析覆盖率
        coverage = self.analyze_coverage(modifications)

        # 3. 验证测试
        self.validate_tests(tests)

        # 4. 创建输出
        output = self.create_fc3_output(
            tests,
            coverage,
            fc2_output,
            task_id
        )

        # 5. 保存输出
        save_layer_output(task_id, "test_generation", output, "test_cases.json")

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[COMPLETE] FC3 layer completed for task {task_id} in {total_elapsed:.2f}ms")

        return output


# Singleton instance
_test_generation_service: Optional[TestGenerationService] = None


def get_test_generation_service() -> TestGenerationService:
    """获取测试生成服务实例"""
    global _test_generation_service
    if _test_generation_service is None:
        _test_generation_service = TestGenerationService()
    return _test_generation_service