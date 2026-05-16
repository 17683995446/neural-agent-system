"""
输出层服务 - MD文档生成层
整合代码生成层与测试生成层的输出，生成结构化Markdown文档
LLM优先智能报告生成，降级到模板拼接
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import jinja2

from app.core.llm_client import create_llm_client
from app.core.logging import logger

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)


class DocumentTemplate:
    """文档模板"""

    _report_template = _jinja_env.get_template("report.md.j2")
    _summary_template = _jinja_env.get_template("summary.md.j2")

    @staticmethod
    def generate_task_report(
        task_id: str,
        user_requirement: str,
        fc1_output: Dict[str, Any],
        fc2_output: Dict[str, Any],
        fc3_output: Dict[str, Any],
        execution_time_ms: float
    ) -> str:
        """生成任务报告文档"""
        modifications = fc2_output.get("modifications", [])
        mod_items = []
        for idx, mod in enumerate(modifications, 1):
            mod_items.append({
                "target": mod.get("target", "unknown"),
                "file_path": mod.get("file_path", "unknown"),
                "status": mod.get("status", "unknown"),
                "diff": mod.get("diff") if mod.get("status") == "success" and "diff" in mod else None,
            })

        tests = fc3_output.get("tests", [])
        test_items = []
        for idx, test in enumerate(tests, 1):
            test_items.append({
                "test_type_title": test.get("test_type", "unknown").title(),
                "target": test.get("target", "unknown"),
                "test_path": test.get("test_file_path", "unknown"),
                "test_code": test.get("test_code") if "test_code" in test else None,
            })

        solution = fc1_output.get("solution", {})
        architecture = solution.get("architecture", {})
        main_components = architecture.get("main_components", [])

        risk_points = []
        for risk in solution.get("risk_points", []):
            risk_points.append({
                "type": risk.get("type", "unknown"),
                "description": risk.get("description", ""),
                "severity": risk.get("severity", "unknown").upper(),
            })

        coverage = fc3_output.get("coverage", {})

        return DocumentTemplate._report_template.render(
            task_id=task_id,
            user_requirement=user_requirement,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            execution_time_ms=f"{execution_time_ms:.2f}",
            fc2_summary=fc2_output.get("summary", {}),
            modifications=enumerate(mod_items, 1),
            coverage_percent=coverage.get("coverage_percent", 0),
            covered_lines=coverage.get("covered_lines", 0),
            total_lines=coverage.get("total_lines", 0),
            tests=enumerate(test_items, 1),
            main_components=main_components,
            risk_points=risk_points,
        )

    @staticmethod
    def generate_simple_summary(
        task_id: str,
        user_requirement: str,
        fc2_output: Dict[str, Any],
        fc3_output: Dict[str, Any]
    ) -> str:
        """生成简化摘要"""
        modifications = fc2_output.get("modifications", [])[:10]
        file_list = "\n".join(
            f"- {m.get('file_path', 'unknown')}" for m in modifications
        )

        return DocumentTemplate._summary_template.render(
            task_id=task_id,
            user_requirement=user_requirement,
            successful=fc2_output.get("summary", {}).get("successful", 0),
            failed=fc2_output.get("summary", {}).get("failed", 0),
            total_tests=fc3_output.get("summary", {}).get("total_tests", 0),
            coverage_percent=fc3_output.get("coverage", {}).get("coverage_percent", 0),
            file_list=file_list,
        )


class OutputLayerService:
    """输出层服务"""

    def __init__(self):
        self.template = DocumentTemplate()
        self.llm_client = create_llm_client()

    def generate_document_with_llm(
        self,
        task_id: str,
        user_requirement: str,
        fc1_output: Dict[str, Any],
        fc2_output: Dict[str, Any],
        fc3_output: Dict[str, Any],
        execution_time_ms: float
    ) -> Optional[str]:
        """LLM优先生成报告，降级到模板"""
        if not self.llm_client.is_available:
            return None
        try:
            mods = fc2_output.get("modifications", [])
            tests = fc3_output.get("tests", [])
            mod_summary = f"{len(mods)} modifications ({sum(1 for m in mods if m.get('status')=='success')} success)"
            test_summary = f"{len(tests)} tests, coverage {fc3_output.get('coverage',{}).get('coverage_percent',0)}%"
            overview = fc1_output.get("solution", {}).get("overview", "")

            prompt = f"""你是技术文档专家。生成一份结构化的Markdown代码修改报告。

任务ID: {task_id}
用户需求: {user_requirement}
方案概述: {overview}
修改: {mod_summary}
测试: {test_summary}

修改详情:
{chr(10).join(f"- {m.get('target','?')} @ {m.get('file_path','?')} [{m.get('status','?')}] by={m.get('generated_by','rule')}" for m in mods[:15])}

请生成完整的Markdown报告，包含任务概述、修改清单、测试结果、建议。只输出Markdown。"""
            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=4096
            )
            text = self.llm_client.get_response_text(response)
            if text and len(text) > 200:
                logger.info(f"[LLM] Output: report generated ({len(text)} chars)")
                return text
            return None
        except Exception as e:
            logger.warning(f"[LLM] Output report generation failed: {e}")
            return None

    def generate_document(
        self,
        task_id: str,
        user_requirement: str,
        fc1_output: Dict[str, Any],
        fc2_output: Dict[str, Any],
        fc3_output: Dict[str, Any],
        execution_time_ms: float
    ) -> str:
        """生成Markdown文档 - LLM优先，降级到模板"""
        start_time = time.time()

        llm_doc = self.generate_document_with_llm(
            task_id, user_requirement, fc1_output, fc2_output, fc3_output, execution_time_ms
        )
        if llm_doc:
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"[TIMING] Document generation (LLM) completed in {elapsed:.2f}ms")
            return llm_doc

        doc = self.template.generate_task_report(
            task_id,
            user_requirement,
            fc1_output,
            fc2_output,
            fc3_output,
            execution_time_ms
        )

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Document generation (template) completed in {elapsed:.2f}ms")

        return doc

    def save_document(
        self,
        task_id: str,
        content: str
    ) -> str:
        """保存文档到文件"""
        start_time = time.time()

        output_dir = Path("task_output") / task_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        doc_path = output_dir / "task_report.md"
        doc_path.write_text(content, encoding="utf-8")

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Document saved to {doc_path} in {elapsed:.2f}ms")

        return str(doc_path)

    def create_output_metadata(
        self,
        task_id: str,
        doc_path: str,
        fc2_output: Dict[str, Any],
        fc3_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建输出元数据"""
        return {
            "task_id": task_id,
            "layer": "output",
            "document_path": doc_path,
            "statistics": {
                "total_modifications": fc2_output.get("summary", {}).get("total_modifications", 0),
                "successful_modifications": fc2_output.get("summary", {}).get("successful", 0),
                "total_tests": fc3_output.get("summary", {}).get("total_tests", 0),
                "coverage_percent": fc3_output.get("coverage", {}).get("coverage_percent", 0)
            },
            "created_at": datetime.now().isoformat()
        }

    def process_task(
        self,
        task_id: str,
        user_requirement: str,
        fc1_output: Dict[str, Any],
        fc2_output: Dict[str, Any],
        fc3_output: Dict[str, Any],
        execution_time_ms: float
    ) -> Dict[str, Any]:
        """处理任务 - 执行完整的输出层流程"""
        start_time = time.time()
        logger.info(f"[START] Output layer processing task {task_id}")

        doc_content = self.generate_document(
            task_id,
            user_requirement,
            fc1_output,
            fc2_output,
            fc3_output,
            execution_time_ms
        )

        doc_path = self.save_document(task_id, doc_content)

        metadata = self.create_output_metadata(task_id, doc_path, fc2_output, fc3_output)

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[COMPLETE] Output layer completed for task {task_id} in {total_elapsed:.2f}ms")

        return metadata


_output_service: Optional[OutputLayerService] = None


def get_output_service() -> OutputLayerService:
    """获取输出层服务实例"""
    global _output_service
    if _output_service is None:
        _output_service = OutputLayerService()
    return _output_service
