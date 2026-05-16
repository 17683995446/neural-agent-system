"""
ModularSolutionPlanner — 分模块三层规划
Step 1: 模块级(1次LLM) → 选择要修改的模块
Step 2: 文件级(每模块1次LLM) → 选择要修改的文件
Step 3: 函数级(每文件1次LLM) → 生成具体修改方案
"""
from typing import Any, Dict, List

from app.core.logging import logger


class ModularSolutionPlanner:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def plan(
        self,
        user_requirement: str,
        module_summaries: List[Dict],
        file_summaries: List[Dict],
        function_details: List[Dict],
    ) -> Dict:
        target_modules = self._plan_modules(user_requirement, module_summaries)
        target_files = self._plan_files(user_requirement, target_modules, file_summaries)
        solution = self._plan_functions(user_requirement, target_files, function_details)
        return solution

    def _plan_modules(
        self, requirement: str, modules: List[Dict]
    ) -> List[str]:
        if not self.llm_client or not getattr(self.llm_client, "is_available", False):
            return [m["name"] for m in modules[:5]]

        module_list = "\n".join(
            f"  - {m['name']}: {m.get('summary', '')} "
            f"({m.get('file_count', 0)} files, deps={m.get('dependencies', [])})"
            for m in modules
        )

        prompt = (
            f"你是项目架构师。根据用户需求，判断哪些模块需要修改。\n\n"
            f"用户需求: {requirement}\n\n"
            f"项目模块:\n{module_list}\n\n"
            f'返回JSON: {{"target_modules": ["模块名1", "模块名2"], "reason": "选择理由"}}\n'
            f"只返回JSON。"
        )

        try:
            result = self.llm_client.complete_json(
                messages=[{"role": "user", "content": prompt}],
                fallback={"target_modules": [m["name"] for m in modules[:5]]},
                agent_name="fc1_module_plan",
            )
            return result.get("target_modules", [m["name"] for m in modules[:5]])
        except Exception as e:
            logger.warning("ModularSolutionPlanner._plan_modules failed: %s", e)
            return [m["name"] for m in modules[:5]]

    def _plan_files(
        self,
        requirement: str,
        target_modules: List[str],
        file_summaries: List[Dict],
    ) -> List[Dict]:
        relevant_files = [
            f for f in file_summaries
            if any(m in f.get("file_path", "") for m in target_modules)
        ]

        if not relevant_files:
            relevant_files = file_summaries[:50]

        if not self.llm_client or not getattr(self.llm_client, "is_available", False):
            return relevant_files[:30]

        file_list = "\n".join(
            f"  - {f['file_path']}: funcs={[fn for fn in f.get('functions', [])[:10]]}, "
            f"classes={[cn for cn in f.get('classes', [])[:5]]}"
            for f in relevant_files[:100]
        )

        prompt = (
            f"你是代码分析师。根据用户需求，判断哪些文件需要修改。\n\n"
            f"用户需求: {requirement}\n\n"
            f"相关文件:\n{file_list}\n\n"
            f'返回JSON: {{"target_files": ["文件路径1", ...], "modification_overview": "修改概述"}}\n'
            f"只返回JSON。"
        )

        try:
            result = self.llm_client.complete_json(
                messages=[{"role": "user", "content": prompt}],
                fallback={"target_files": [f["file_path"] for f in relevant_files[:20]]},
                agent_name="fc1_file_plan",
            )
            target_paths = result.get("target_files", [])
            return [f for f in relevant_files if f["file_path"] in target_paths]
        except Exception as e:
            logger.warning("ModularSolutionPlanner._plan_files failed: %s", e)
            return relevant_files[:20]

    def _plan_functions(
        self,
        requirement: str,
        target_files: List[Dict],
        function_details: List[Dict],
    ) -> Dict:
        func_info = "\n".join(
            f"  - {fd['name']} in {fd['file_path']} (line {fd.get('line', '?')})"
            for fd in function_details[:50]
        )

        target_file_list = "\n".join(
            f"  - {f['file_path']}" for f in target_files[:30]
        )

        if not self.llm_client or not getattr(self.llm_client, "is_available", False):
            return self._generate_rule_fallback(requirement, target_files)

        prompt = (
            f"你是代码修改专家。根据用户需求和代码结构，生成修改方案。\n\n"
            f"用户需求: {requirement}\n\n"
            f"相关函数:\n{func_info}\n\n"
            f"目标文件:\n{target_file_list}\n\n"
            f"返回JSON:\n"
            f'{{"overview": "方案概述", '
            f'"modification_list": ['
            f'{{"type": "function", "target": "函数名", "file": "文件路径", '
            f'"action": "修改动作", "priority": "high/medium/low"}}], '
            f'"execution_order": ["target1", "target2"], '
            f'"risk_points": [{{"type": "风险类型", "severity": "high/medium/low"}}]}}\n'
            f"只返回JSON。"
        )

        try:
            result = self.llm_client.complete_json(
                messages=[{"role": "user", "content": prompt}],
                fallback=self._generate_rule_fallback(requirement, target_files),
                agent_name="fc1_func_plan",
                max_tokens=4096,
            )
            if "modification_list" not in result:
                return self._generate_rule_fallback(requirement, target_files)
            return result
        except Exception as e:
            logger.warning("ModularSolutionPlanner._plan_functions failed: %s", e)
            return self._generate_rule_fallback(requirement, target_files)

    @staticmethod
    def _generate_rule_fallback(
        requirement: str, target_files: List[Dict]
    ) -> Dict:
        modification_list = [
            {
                "type": "file",
                "target": f.get("file_path", ""),
                "file": f.get("file_path", ""),
                "action": "modify",
                "priority": "medium",
            }
            for f in target_files[:20]
        ]
        return {
            "overview": f"Rule-based plan: modify {len(modification_list)} files for: {requirement[:100]}",
            "modification_list": modification_list,
            "execution_order": [m["target"] for m in modification_list],
            "risk_points": [],
        }
