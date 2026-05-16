"""
全连接层1 - 全局代码理解层
整合池化层输出，结合历史经验生成可落地的任务执行方案
LLM优先调用，失败时降级到规则引擎
"""
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.agents.memory.long_term import get_long_term_memory
from app.core.llm_client import create_llm_client
from app.core.llm_utils import extract_json_from_llm_response
from app.core.io_utils import save_layer_output
from app.core.logging import logger
from app.core.cheap_llm_client import CheapLLMClient
from app.models.modification import SubRequirement, ModificationItem
from app.services.fullconnect.modular_planner import ModularSolutionPlanner
from app.core.code_index import CodeStructureIndex


class GlobalUnderstandingConfig:
    """全局理解配置"""
    def __init__(
        self,
        similar_experience_top_k: int = 5,
        similarity_threshold: float = 0.7
    ):
        self.similar_experience_top_k = similar_experience_top_k
        self.similarity_threshold = similarity_threshold


class SolutionPlanner:
    """方案规划器 - LLM优先生成修改方案，降级到规则引擎"""

    MAX_SNIPPET_LINES = 30
    MAX_SNIPPET_CHARS = 4000

    def __init__(self):
        self.llm_client = create_llm_client()

    def _collect_key_snippets(
        self, top_functions: List[Dict], top_classes: List[Dict]
    ) -> str:
        """从源文件中提取关键函数/类的小代码片段，内联到FC1规划prompt"""
        snippets = []
        total_chars = 0
        seen_files = set()

        for item in top_functions + top_classes:
            if total_chars >= self.MAX_SNIPPET_CHARS:
                break
            file_path = item.get("file", "")
            if not file_path or file_path in seen_files:
                continue
            seen_files.add(file_path)

            try:
                from pathlib import Path
                p = Path(file_path)
                if not p.exists():
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
                target_line = item.get("line") or item.get("relevance", 0)
                if isinstance(target_line, int) and target_line > 0:
                    start = max(0, target_line - 1)
                    end = min(len(lines), start + self.MAX_SNIPPET_LINES)
                    snippet = "\n".join(lines[start:end])
                else:
                    snippet = "\n".join(lines[:self.MAX_SNIPPET_LINES])

                name = item.get("name", "?")
                if len(snippet) + total_chars <= self.MAX_SNIPPET_CHARS:
                    snippets.append(f"# --- {name} in {file_path} ---\n{snippet}")
                    total_chars += len(snippet) + 50
            except Exception:
                pass

        return "\n\n".join(snippets)

    def generate_solution(
        self,
        user_requirement: str,
        global_features: Dict[str, Any],
        similar_experiences: List[Dict[str, Any]],
        sub_requirement: Optional[SubRequirement] = None,
    ) -> Dict[str, Any]:
        effective_req = sub_requirement.description if sub_requirement else user_requirement
        scope_hint = sub_requirement.scope_hint if sub_requirement else ""

        if self.llm_client.is_available:
            llm_solution = self._generate_solution_llm(
                effective_req, global_features, similar_experiences, scope_hint=scope_hint
            )
            if llm_solution:
                if sub_requirement:
                    for mod in llm_solution.get("modification_list", []):
                        mod["sub_requirement_id"] = sub_requirement.id
                return llm_solution

        solution = self._generate_solution_rule(effective_req, global_features, similar_experiences)
        if sub_requirement:
            for mod in solution.get("modification_list", []):
                mod["sub_requirement_id"] = sub_requirement.id
        return solution

    def _generate_solution_llm(
        self,
        user_requirement: str,
        global_features: Dict[str, Any],
        similar_experiences: List[Dict[str, Any]],
        scope_hint: str = "",
    ) -> Optional[Dict[str, Any]]:
        try:
            top_functions = global_features.get("top_functions", [])
            top_classes = global_features.get("top_classes", [])
            unique_imports = global_features.get("unique_imports", [])

            func_info = "\n".join(
                f"  - {f['name']} (file: {f['file']}, line: {f.get('line', '?')})" for f in top_functions[:30]
            )
            class_info = "\n".join(
                f"  - {c['name']} (file: {c['file']}, line: {c.get('line', '?')})" for c in top_classes[:20]
            )

            code_snippets = self._collect_key_snippets(top_functions[:15], top_classes[:10])
            snippets_section = ""
            if code_snippets:
                snippets_section = f"\n关键代码片段:\n```\n{code_snippets}\n```\n"

            imports_section = ""
            if unique_imports:
                imports_preview = "\n".join(unique_imports[:30])
                imports_section = f"\n关键imports:\n{imports_preview}\n"

            prompt = f"""你是代码架构分析专家。根据用户需求和代码结构，生成修改方案。

用户需求: {user_requirement}
{f"重点涉及: {scope_hint}" if scope_hint else ""}

代码结构:
函数:
{func_info if func_info else '  (无)'}

类:
{class_info if class_info else '  (无)'}
{imports_section}{snippets_section}
请生成修改方案，严格按JSON格式返回:
{{
  "overview": "方案概述",
  "modification_list": [
    {{"type": "function/class", "target": "名称", "file": "文件路径", "line": null, "action": "具体修改动作描述", "priority": "high/medium/low"}}
  ],
  "execution_order": ["class:X", "function:Y"],
  "risk_points": [
    {{"type": "风险类型", "description": "描述", "severity": "high/medium/low"}}
  ]
}}

只返回JSON，不要其他内容。"""

            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096
            )
            text = self.llm_client.get_response_text(response)
            if not text:
                return None

            solution = extract_json_from_llm_response(text, fallback=None)
            if solution is None:
                return None

            if "modification_list" not in solution:
                return None

            for mod in solution.get("modification_list", []):
                mod.setdefault("line", None)
                mod.setdefault("action", "analyze_and_modify")
                mod.setdefault("priority", "medium")

            solution["similar_experiences_used"] = len(similar_experiences)
            logger.info(f"[LLM] FC1 solution generated: {len(solution.get('modification_list', []))} modifications")
            return solution

        except Exception as e:
            logger.warning(f"[LLM] FC1 solution generation failed, falling back to rules: {e}")
            return None

    def _generate_solution_rule(
        self,
        user_requirement: str,
        global_features: Dict[str, Any],
        similar_experiences: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        logger.info("[FC1] Using rule-based solution generation")
        solution = {
            "overview": self._generate_overview(user_requirement, global_features),
            "modification_list": self._generate_modification_list(global_features),
            "execution_order": self._generate_execution_order(global_features),
            "risk_points": self._identify_risk_points(global_features),
            "similar_experiences_used": len(similar_experiences)
        }
        return solution

    def _generate_overview(
        self,
        user_requirement: str,
        global_features: Dict[str, Any]
    ) -> str:
        """生成方案概述"""
        total_files = global_features.get("total_files", 0)
        total_functions = global_features.get("total_functions", 0)
        total_classes = global_features.get("total_classes", 0)

        return (
            f"根据用户需求「{user_requirement}」，"
            f"分析得到代码工程包含 {total_files} 个文件、"
            f"{total_functions} 个函数、{total_classes} 个类。"
            f"将进行针对性的代码修改。"
        )

    def _generate_modification_list(
        self,
        global_features: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """生成修改清单"""
        modifications = []

        top_functions = global_features.get("top_functions", [])
        top_classes = global_features.get("top_classes", [])

        # 为每个顶级函数生成修改建议
        for func in top_functions[:10]:
            modifications.append({
                "type": "function",
                "target": func["name"],
                "file": func["file"],
                "line": func.get("line"),
                "action": "analyze_and_modify",
                "priority": "high" if self._is_critical_function(func["name"]) else "medium"
            })

        # 为每个顶级类生成修改建议
        for cls in top_classes[:10]:
            modifications.append({
                "type": "class",
                "target": cls["name"],
                "file": cls["file"],
                "line": cls.get("line"),
                "action": "analyze_and_modify",
                "priority": "high" if self._is_critical_class(cls["name"]) else "medium"
            })

        return modifications

    def _is_critical_function(self, name: str) -> bool:
        """判断是否为关键函数"""
        critical_patterns = {
            "auth", "login", "logout", "verify", "validate",
            "check", "parse", "execute", "process", "handle"
        }
        name_lower = name.lower()
        return any(p in name_lower for p in critical_patterns)

    def _is_critical_class(self, name: str) -> bool:
        """判断是否为关键类"""
        critical_patterns = {
            "Manager", "Handler", "Service", "Controller",
            "Processor", "Engine", "Core", "Base"
        }
        return any(p in name for p in critical_patterns)

    def _generate_execution_order(
        self,
        global_features: Dict[str, Any]
    ) -> List[str]:
        """生成执行顺序"""
        order = []

        top_classes = global_features.get("top_classes", [])
        top_functions = global_features.get("top_functions", [])

        # 先处理类（架构层面）
        for cls in top_classes[:5]:
            order.append(f"class:{cls['name']}")

        # 再处理函数（功能层面）
        for func in top_functions[:10]:
            order.append(f"function:{func['name']}")

        return order

    def _identify_risk_points(
        self,
        global_features: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """识别风险点"""
        risks = []

        # 检查依赖关系风险
        imports = global_features.get("unique_imports", [])
        if len(imports) > 30:
            risks.append({
                "type": "high_dependency",
                "description": "项目依赖较多，可能存在隐式依赖",
                "severity": "medium"
            })

        # 检查文件大小风险
        top_functions = global_features.get("top_functions", [])
        large_funcs = [f for f in top_functions if (f.get("line") or 0) > 100]
        if large_funcs:
            risks.append({
                "type": "large_functions",
                "description": f"存在 {len(large_funcs)} 个较大的函数",
                "severity": "low"
            })

        return risks


class GlobalUnderstandingService:
    """全局代码理解层服务"""

    def __init__(
        self,
        agent_id: str = "global_understanding_agent",
        config: Optional[GlobalUnderstandingConfig] = None
    ):
        self.agent_id = agent_id
        self.config = config or GlobalUnderstandingConfig()
        self.planner = SolutionPlanner()
        self._modular_planner: Optional[ModularSolutionPlanner] = None
        self._cheap_mode: bool = False
        self.long_term_memory = None

    def enable_cheap_llm(self):
        """启用极便宜LLM — ModularSolutionPlanner用CheapLLMClient"""
        self._modular_planner = ModularSolutionPlanner(CheapLLMClient())
        self._cheap_mode = True
        logger.info("FC1: cheap LLM mode enabled")

    def _get_long_term_memory(self):
        """获取长期记忆"""
        if self.long_term_memory is None:
            self.long_term_memory = get_long_term_memory(self.agent_id)
        return self.long_term_memory

    def retrieve_similar_experiences(
        self,
        user_requirement: str
    ) -> List[Dict[str, Any]]:
        """召回相似历史经验"""
        start_time = time.time()

        try:
            memory = self._get_long_term_memory()
            experiences = memory.get_similar_experiences(
                user_requirement=user_requirement,
                top_k=self.config.similar_experience_top_k,
                task_type="code_modification"
            )

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"[TIMING] Retrieved {len(experiences)} similar experiences in {elapsed:.2f}ms")

            return experiences
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.warning(f"[TIMING] Failed to retrieve experiences in {elapsed:.2f}ms: {e}")
            return []

    def analyze_architecture(
        self,
        global_features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """分析代码架构"""
        start_time = time.time()

        top_classes = global_features.get("top_classes", [])
        top_functions = global_features.get("top_functions", [])

        architecture = {
            "main_components": [c["name"] for c in top_classes[:5]],
            "main_functions": [f["name"] for f in top_functions[:10]],
            "entry_points": self._identify_entry_points(top_functions),
            "data_flow": self._analyze_data_flow(top_functions, top_classes)
        }

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Architecture analysis completed in {elapsed:.2f}ms")

        return architecture

    def _identify_entry_points(self, functions: List[Dict]) -> List[str]:
        """识别入口点"""
        entry_patterns = {"main", "run", "start", "init", "execute", "process"}
        entries = []

        for func in functions:
            name = func.get("name", "").lower()
            if any(p in name for p in entry_patterns):
                entries.append(func["name"])

        return entries[:5]

    def _analyze_data_flow(
        self,
        functions: List[Dict],
        classes: List[Dict]
    ) -> Dict[str, Any]:
        """分析数据流"""
        return {
            "note": "Simplified data flow analysis",
            "estimated_flows": len(functions) // 5
        }

    def generate_solution(
        self,
        user_requirement: str,
        global_features: Dict[str, Any],
        pooling_output: Dict[str, Any],
        sub_requirements: Optional[List[SubRequirement]] = None,
    ) -> Dict[str, Any]:
        """生成代码修改方案 — 按sub_requirement逐个规划后合并"""
        start_time = time.time()

        similar_experiences = self.retrieve_similar_experiences(user_requirement)

        if sub_requirements and len(sub_requirements) > 1:
            merged_mods = []
            all_risks = []
            overview_parts = []

            for sub in sub_requirements:
                sub_solution = self._generate_single_solution(
                    user_requirement, global_features, pooling_output,
                    similar_experiences, sub,
                )
                mods = sub_solution.get("modification_list", [])
                merged_mods.extend(mods)
                all_risks.extend(sub_solution.get("risk_points", []))
                overview_parts.append(sub_solution.get("overview", ""))

            deduped_mods, conflict_stats = self._merge_modification_lists(merged_mods)

            solution = {
                "overview": " | ".join(overview_parts) if overview_parts else user_requirement,
                "modification_list": deduped_mods,
                "risk_points": all_risks[:10],
                "similar_experiences_used": len(similar_experiences),
                "sub_requirements_count": len(sub_requirements),
                "merge_conflicts": conflict_stats,
            }
            architecture = self.analyze_architecture(global_features)
            solution["architecture"] = architecture
            elapsed = (time.time() - start_time) * 1000
            logger.info(
                "[TIMING] Multi-sub-requirement solution: %d mods from %d subs in %.2fms",
                len(deduped_mods), len(sub_requirements), elapsed,
            )
            return solution

        sub_req = sub_requirements[0] if sub_requirements else None
        solution = self._generate_single_solution(
            user_requirement, global_features, pooling_output,
            similar_experiences, sub_req,
        )

        architecture = self.analyze_architecture(global_features)
        solution["architecture"] = architecture

        self._save_experience_to_long_term_memory(
            user_requirement, solution, sub_requirement
        )

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Solution generation completed in {elapsed:.2f}ms")

        return solution

    @staticmethod
    def _save_experience_to_long_term_memory(
        user_requirement: str,
        solution: Dict[str, Any],
        sub_requirement: Optional[SubRequirement] = None,
    ):
        """将方案规划经验保存到长期记忆，供后续任务检索学习"""
        try:
            from app.agents.memory.long_term import get_long_term_memory
            ltm = get_long_term_memory()
            if ltm is None:
                return
            task_type = sub_requirement.scope_hint if sub_requirement and sub_requirement.scope_hint else "general"
            mod_count = len(solution.get("modification_list", []))
            result_summary = f"planned {mod_count} modifications: overview={solution.get('overview', '')[:200]}"
            ltm.save_task_experience(
                task_id=sub_requirement.id if sub_requirement else "unknown",
                task_type=task_type,
                user_requirement=user_requirement,
                result=result_summary,
                user_feedback={"modification_count": mod_count},
            )
            logger.debug("Saved planning experience to long-term memory (type=%s)", task_type)
        except Exception as e:
            logger.debug("Failed to save experience to long-term memory: %s", e)

    @staticmethod
    def _query_code_index(global_features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从CodeStructureIndex查询top函数/类的结构化知识：调用链+继承+装饰器"""
        try:
            index = CodeStructureIndex()
            stats = index.get_stats()
            if stats.get("symbol_count", 0) == 0:
                return None

            top_functions = global_features.get("top_functions", [])[:20]
            top_classes = global_features.get("top_classes", [])[:10]

            enriched_symbols = []
            for func in top_functions:
                name = func.get("name", "") if isinstance(func, dict) else str(func)
                if not name:
                    continue
                enriched = index.query_enriched_symbol(name)
                enriched["source"] = "function"
                enriched_symbols.append(enriched)

            for cls in top_classes:
                name = cls.get("name", "") if isinstance(cls, dict) else str(cls)
                if not name:
                    continue
                enriched = index.query_enriched_symbol(name)
                enriched["source"] = "class"
                enriched_symbols.append(enriched)

            api_routes = index.query_by_decorator("get") + index.query_by_decorator("post") + index.query_by_decorator("put") + index.query_by_decorator("delete")

            return {
                "enriched_symbols": enriched_symbols[:30],
                "api_routes": api_routes[:20],
                "index_stats": stats,
            }
        except Exception as e:
            logger.debug("FC1 code index query failed: %s", e)
            return None

    @staticmethod
    def _merge_modification_lists(
        merged_mods: List[Dict[str, Any]],
    ) -> tuple:
        """合并多子需求的modification_list：区域级冲突检测+解决
        返回 (deduped_mods, conflict_stats)
        """
        file_groups: Dict[str, List[Dict]] = {}
        for mod in merged_mods:
            fp = mod.get("file", "")
            file_groups.setdefault(fp, []).append(mod)

        result_mods = []
        conflicts_detected = 0
        conflicts_resolved = 0
        modifications_lost = 0

        for fp, file_mods in file_groups.items():
            if len(file_mods) == 1:
                result_mods.extend(file_mods)
                continue

            file_mods.sort(key=lambda m: (0 if m.get("priority") == "high" else 1 if m.get("priority") == "medium" else 2))

            by_target: Dict[str, List[Dict]] = {}
            for mod in file_mods:
                target = mod.get("target", "")
                by_target.setdefault(target, []).append(mod)

            for target, target_mods in by_target.items():
                if len(target_mods) == 1:
                    result_mods.extend(target_mods)
                    continue

                sub_ids = [m.get("sub_requirement_id", "") for m in target_mods]
                unique_subs = set(s for s in sub_ids if s)

                if len(unique_subs) <= 1:
                    best = target_mods[0]
                    for m in target_mods[1:]:
                        modifications_lost += 1
                        logger.warning(
                            "[FC1-MERGE] Duplicate (file=%s, target=%s) from same sub_req, keeping first",
                            fp, target,
                        )
                    result_mods.append(best)
                    continue

                lines_list = []
                for m in target_mods:
                    line = m.get("line")
                    if line and isinstance(line, int) and line > 0:
                        lines_list.append((line, m))

                if len(lines_list) == len(target_mods):
                    sorted_by_line = sorted(lines_list, key=lambda x: x[0])
                    has_overlap = False
                    prev_end = 0
                    for line_num, m in sorted_by_line:
                        est_size = 30
                        if line_num < prev_end:
                            has_overlap = True
                            break
                        prev_end = line_num + est_size

                    if not has_overlap:
                        for _, m in sorted_by_line:
                            m["conflict"] = False
                            result_mods.append(m)
                        conflicts_resolved += len(target_mods)
                        logger.info(
                            "[FC1-MERGE] Same file non-overlapping mods for target=%s: %d items kept",
                            target, len(target_mods),
                        )
                        continue

                conflicts_detected += 1
                best = target_mods[0]
                best["conflict"] = True
                best["conflict_with"] = [
                    {"target": m.get("target"), "sub_requirement_id": m.get("sub_requirement_id"), "action": m.get("action")}
                    for m in target_mods[1:]
                ]
                result_mods.append(best)

                for m in target_mods[1:]:
                    merge_mod = dict(m)
                    merge_mod["action"] = "refactor_merge"
                    merge_mod["priority"] = "high"
                    merge_mod["conflict"] = True
                    merge_mod["merge_predecessor"] = {
                        "target": best.get("target"),
                        "sub_requirement_id": best.get("sub_requirement_id"),
                        "action": best.get("action"),
                    }
                    result_mods.append(merge_mod)
                    conflicts_resolved += 1

                logger.warning(
                    "[FC1-MERGE] Conflict: %d mods for (file=%s, target=%s) from sub_reqs %s → refactor_merge",
                    len(target_mods), fp, target, unique_subs,
                )

        result_mods.sort(key=lambda m: (0 if m.get("priority") == "high" else 1 if m.get("priority") == "medium" else 2))

        conflict_stats = {
            "conflicts_detected": conflicts_detected,
            "conflicts_resolved": conflicts_resolved,
            "modifications_lost": modifications_lost,
        }
        logger.info(
            "[FC1-MERGE] Merge complete: %d mods, conflicts=%d resolved=%d lost=%d",
            len(result_mods), conflicts_detected, conflicts_resolved, modifications_lost,
        )
        return result_mods, conflict_stats

    def _generate_single_solution(
        self,
        user_requirement: str,
        global_features: Dict[str, Any],
        pooling_output: Dict[str, Any],
        similar_experiences: List[Dict[str, Any]],
        sub_requirement: Optional[SubRequirement] = None,
    ) -> Dict[str, Any]:
        code_index_knowledge = self._query_code_index(global_features)
        if code_index_knowledge:
            global_features["code_index_knowledge"] = code_index_knowledge

        if global_features.get("hierarchical"):
            module_summaries = global_features.get("module_summaries", [])
            file_summaries = global_features.get("file_summaries", [])
            function_details = global_features.get("function_details", [])

            if module_summaries and file_summaries:
                if self._modular_planner is None:
                    llm = CheapLLMClient() if self._cheap_mode else create_llm_client()
                    self._modular_planner = ModularSolutionPlanner(llm)
                effective_req = sub_requirement.description if sub_requirement else user_requirement
                solution = self._modular_planner.plan(
                    effective_req, module_summaries, file_summaries, function_details
                )
                solution["similar_experiences_used"] = len(similar_experiences)
                if sub_requirement:
                    for mod in solution.get("modification_list", []):
                        mod["sub_requirement_id"] = sub_requirement.id
                return solution

        return self.planner.generate_solution(
            user_requirement, global_features, similar_experiences,
            sub_requirement=sub_requirement,
        )

    def create_fc1_output(
        self,
        solution: Dict[str, Any],
        pooling_output: Dict[str, Any],
        task_id: str
    ) -> Dict[str, Any]:
        """创建全连接层1输出"""
        output = {
            "task_id": task_id,
            "layer": "global_understanding",
            "layer_name": "full_connect_1",
            "solution": solution,
            "pooling_reference": {
                "total_files": pooling_output.get("total_files_processed"),
                "user_requirement": pooling_output.get("user_requirement")
            },
            "created_at": datetime.now().isoformat()
        }

        return output

    def process_task(
        self,
        task_id: str,
        pooling_output: Dict[str, Any],
        user_requirement: str,
        sub_requirements: Optional[List[SubRequirement]] = None,
    ) -> Dict[str, Any]:
        """处理任务 - 执行完整的全局理解层流程"""
        start_time = time.time()
        logger.info(f"[START] FC1 Global Understanding layer processing task {task_id}")

        global_features = pooling_output.get("global_features", {})

        solution = self.generate_solution(
            user_requirement,
            global_features,
            pooling_output,
            sub_requirements=sub_requirements,
        )

        # 2. 创建输出
        output = self.create_fc1_output(solution, pooling_output, task_id)

        # 3. 保存输出
        save_layer_output(task_id, "global_understanding", output, "solution.json")

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[COMPLETE] FC1 layer completed for task {task_id} in {total_elapsed:.2f}ms")

        return output


# Singleton instance
_global_understanding_service: Optional[GlobalUnderstandingService] = None


def get_global_understanding_service() -> GlobalUnderstandingService:
    """获取全局理解服务实例"""
    global _global_understanding_service
    if _global_understanding_service is None:
        _global_understanding_service = GlobalUnderstandingService()
    return _global_understanding_service