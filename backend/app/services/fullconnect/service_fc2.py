"""
全连接层2 - 代码生成层
基于全局理解层的修改方案完成代码生成、修改、优化
LLM优先调用，失败时降级到模板生成
"""
import os
import time
import difflib
import shutil
import subprocess
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agents.trust.manager import get_trust_manager
from app.core.llm_client import create_llm_client
from app.core.llm_utils import extract_code_from_llm_response
from app.core.io_utils import save_layer_output
from app.core.logging import logger
from app.core.cheap_llm_client import CheapLLMClient
from app.core.agent_pool import AgentPool
from app.services.fullconnect.modification_graph import ModificationDependencyGraph
from app.services.fullconnect.smart_context import SmartContextWindow
from app.core.code_index import CodeStructureIndex
from app.core.consensus import ConsensusEngine, ConsensusStrategy

# 并发修改数
MAX_CONCURRENT_MODIFICATIONS = min(int(os.environ.get("MAX_CONCURRENT_MODS", "8")), 8)


class CodeGenerationConfig:
    """代码生成配置"""
    def __init__(
        self,
        trust_threshold_high: float = 0.8,
        trust_threshold_low: float = 0.6,
        max_modifications: int = 50
    ):
        self.trust_threshold_high = trust_threshold_high
        self.trust_threshold_low = trust_threshold_low
        self.max_modifications = max_modifications


class CodeModifier:
    """代码修改器 - LLM优先生成修改，降级到模板"""

    def __init__(self):
        self.llm_client = create_llm_client()

    def generate_modification(
        self,
        modification_item: Dict[str, Any],
        code_context: str
    ) -> Dict[str, Any]:
        modification_item.get("target", "")
        modification_item.get("file", "")
        modification_item.get("action", "")

        if self.llm_client.is_available and code_context and len(code_context) < 10000:
            llm_result = self._generate_modification_llm(
                modification_item, code_context
            )
            if llm_result:
                return llm_result

        return self._generate_modification_template(modification_item, code_context)

    def _generate_modification_llm(
        self,
        modification_item: Dict[str, Any],
        code_context: str
    ) -> Optional[Dict[str, Any]]:
        try:
            target = modification_item.get("target", "")
            file_path = modification_item.get("file", "")
            action = modification_item.get("action", "")

            max_lines = 80
            code_lines = code_context.split("\n")
            truncated_code = "\n".join(
                code_lines[:max_lines]
            )
            if len(code_lines) > max_lines:
                truncated_code += f"\n# ... ({len(code_lines) - max_lines} more lines)"

            prompt = f"""你是代码修改专家。根据需求修改以下代码。

修改目标: {target}
文件: {file_path}
修改动作: {action}

原始代码:
```python
{truncated_code}
```

请输出修改后的完整代码，用```python```包裹。只输出代码，不要解释。"""

            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4096
            )
            text = self.llm_client.get_response_text(response)
            if not text:
                return None

            modified_code = extract_code_from_llm_response(text, language="python")

            if not modified_code or len(modified_code) < 10:
                return None

            diff = self._compute_simple_diff(code_context, modified_code)

            logger.info(f"[LLM] FC2 modification generated for {target}")
            return {
                "original_code": code_context[:500],
                "modified_code": modified_code,
                "diff": diff,
                "file_path": file_path,
                "target": target,
                "generated_by": "llm"
            }

        except Exception as e:
            logger.warning(f"[LLM] FC2 modification failed for {modification_item.get('target')}, falling back: {e}")
            return None

    def _compute_simple_diff(self, original: str, modified: str) -> str:
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(orig_lines, mod_lines, fromfile="original", tofile="modified", lineterm="")
        return "\n".join(diff)

    def _generate_modification_template(
        self,
        modification_item: Dict[str, Any],
        code_context: str
    ) -> Dict[str, Any]:
        target = modification_item.get("target", "")
        file_path = modification_item.get("file", "")
        action = modification_item.get("action", "")
        marker = f"# [NeuralAgent] TODO: {action} {target} (fallback - manual review)\n"
        modified_code = marker + code_context if code_context else marker
        return {
            "original_code": code_context[:500] if code_context else "",
            "modified_code": modified_code,
            "diff": f"[FALLBACK] {action} on {target} - marked for manual review",
            "file_path": file_path,
            "target": target,
            "generated_by": "template",
            "requires_manual_review": True,
        }


class TrustBasedFilter:
    """基于信任度的过滤器"""

    def __init__(self, threshold_high: float = 0.8, threshold_low: float = 0.6):
        self.threshold_high = threshold_high
        self.threshold_low = threshold_low

    def filter_modifications(
        self,
        modifications: List[Dict[str, Any]],
        trust_matrix: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """基于信任度过滤修改项"""
        filtered = []

        for mod in modifications:
            agent_id = mod.get("agent_id", "default")
            trust_score = trust_matrix.get(agent_id, 1.0)

            if trust_score >= self.threshold_high:
                filtered.append({**mod, "trust_level": "high", "need_recheck": False})
            elif trust_score >= self.threshold_low:
                filtered.append({**mod, "trust_level": "medium", "need_recheck": True})
            # trust_score < threshold_low: 完全过滤

        return filtered


class CodeGenerationService:
    """代码生成层服务"""

    def __init__(self, config: Optional[CodeGenerationConfig] = None):
        self.config = config or CodeGenerationConfig()
        self.modifier = CodeModifier()
        self.filter = TrustBasedFilter(
            threshold_high=self.config.trust_threshold_high,
            threshold_low=self.config.trust_threshold_low
        )
        self.trust_manager = get_trust_manager()
        self._mod_graph = ModificationDependencyGraph(code_index=CodeStructureIndex())
        self._smart_context = SmartContextWindow()
        self._consensus_engine = ConsensusEngine(
            strategy=ConsensusStrategy.OVERLAP_RATIO,
            consensus_threshold=0.6,
            similarity_threshold=0.7,
        )
        self._agent_pool: Optional[AgentPool] = None
        self._cheap_mode: bool = False

    def enable_agent_pool(self, max_workers: int = 0):
        """启用无限agent池 — 每修改项一个agent, CheapLLMClient"""
        self._agent_pool = AgentPool(max_workers=max_workers or None)
        self._cheap_mode = True
        logger.info("FC2: agent pool enabled (workers=%d)", self._agent_pool.max_workers)

    def filter_by_trust(
        self,
        modification_list: List[Dict[str, Any]],
        agent_id: str
    ) -> List[Dict[str, Any]]:
        """基于信任度矩阵过滤修改项"""
        start_time = time.time()

        trust_matrix = self.trust_manager.get_trust_matrix(agent_id)
        filtered = self.filter.filter_modifications(modification_list, trust_matrix)

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Trust filtering completed in {elapsed:.2f}ms, kept {len(filtered)}/{len(modification_list)} items")

        return filtered

    def apply_modifications(
        self,
        modification_list: List[Dict[str, Any]],
        code_repo_path: str
    ) -> List[Dict[str, Any]]:
        """应用代码修改 — cheap模式用AgentPool, 否则用依赖图"""
        start_time = time.time()
        results = []

        limited_mods = modification_list[:self.config.max_modifications]

        if self._cheap_mode and self._agent_pool is not None:
            results = self._apply_modifications_with_agent_pool(limited_mods, code_repo_path)
            elapsed = (time.time() - start_time) * 1000
            logger.info("[TIMING] AgentPool applied %d modifications in %.2fms", len(results), elapsed)
            return results

        execution_plan = self._mod_graph.build_execution_plan(limited_mods)
        file_state: Dict[str, str] = {}

        for batch_idx, batch in enumerate(execution_plan):
            groups = ModificationDependencyGraph.get_sequential_groups(batch)

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_MODIFICATIONS) as executor:
                future_to_key = {}
                for group_key, group_mods in groups.items():
                    future = executor.submit(
                        self._apply_sequential_modifications,
                        group_mods, code_repo_path, file_state
                    )
                    future_to_key[future] = group_key

                for future in concurrent.futures.as_completed(future_to_key):
                    try:
                        batch_results = future.result()
                        results.extend(batch_results)
                        for r in batch_results:
                            if r.get("status") == "success" and "modified_code" in r:
                                fp = r.get("file_path", "") or r.get("file", "")
                                if fp:
                                    file_state[fp] = r["modified_code"]
                    except Exception as e:
                        logger.error("Batch modification failed: %s", e)

            logger.info(
                "Execution batch %d/%d: %d results",
                batch_idx + 1, len(execution_plan), len(results),
            )

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[TIMING] Applied {len(results)} modifications in {total_elapsed:.2f}ms")

        return results

    def _apply_modifications_with_agent_pool(
        self,
        modifications: List[Dict[str, Any]],
        code_repo_path: str,
    ) -> List[Dict[str, Any]]:
        """AgentPool模式: 每修改项一个agent, 独立CheapLLMClient"""
        code_repo_ref = code_repo_path

        def apply_one(mod: Dict[str, Any]) -> Dict[str, Any]:
            cheap = CheapLLMClient()
            try:
                fp = mod.get("file", "")
                full_path = Path(code_repo_ref) / fp
                code_context = ""
                if full_path.exists():
                    code_context = full_path.read_text(encoding="utf-8")
                    backup_path = Path(code_repo_ref) / f"{fp}.bak"
                    shutil.copy2(full_path, backup_path)
                else:
                    code_context = f"# File not found: {fp}"

                target = mod.get("target", "")
                action = mod.get("action", "modify")
                if target:
                    code_context = self._smart_context.get_context(full_path, target, code_context)

                code_preview = code_context[:6000]
                prompt = (
                    f"修改文件 {fp} 中的 {target}:\n"
                    f"动作: {action}\n"
                    f"代码:\n```python\n{code_preview}\n```\n"
                    f"输出修改后的完整代码, 用```python```包裹。只输出代码。"
                )
                response = cheap.complete(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048,
                )
                text = cheap.get_response_text(response)
                if text:
                    modified_code = extract_code_from_llm_response(text, language="python")
                    if modified_code:
                        self._write_modification(full_path, modified_code)
                        return {
                            "target": target, "file": fp, "status": "success",
                            "modified_code": modified_code, "generated_by": "cheap_llm",
                        }
            except Exception as e:
                logger.debug("CheapLLM mod failed for %s: %s", mod.get("target"), e)
            return {
                "target": mod.get("target", ""), "file": mod.get("file", ""),
                "status": "fallback", "requires_manual_review": True,
            }

        agent_results = self._agent_pool.dispatch_simple(apply_one, modifications)
        return self._agent_pool.aggregate(agent_results, strategy="all")

    def _apply_sequential_modifications(
        self,
        mods: List[Dict[str, Any]],
        code_repo_path: str,
        file_state: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """同文件串行修改: 后续修改基于前次修改结果(diff/patch模式)"""
        results = []
        for mod in mods:
            mod_start = time.time()
            llm_client = create_llm_client()
            try:
                fp = mod.get("file", "")
                full_path = Path(code_repo_path) / fp

                code_context = file_state.get(fp)
                if code_context is None:
                    if full_path.exists():
                        code_context = full_path.read_text(encoding="utf-8")
                        backup_path = Path(code_repo_path) / f"{fp}.bak"
                        shutil.copy2(full_path, backup_path)
                    else:
                        code_context = f"# File not found: {fp}"

                target = mod.get("target", "")
                action = mod.get("action", "")
                is_merge = action == "refactor_merge"

                if target and not is_merge:
                    code_context = self._smart_context.get_context(
                        full_path, target, code_context
                    )

                modification = self._generate_modification_with_client(llm_client, mod, code_context)
                modification["status"] = "success"

                action = mod.get("action", "")
                is_critical_action = action in ("modify", "refactor_merge", "refactor")
                if is_critical_action and self._agent_pool is not None:
                    modification = self._apply_with_consensus(
                        llm_client, mod, code_context, modification
                    )

                if modification.get("modified_code") and modification.get("generated_by") == "llm":
                    original_code = file_state.get(fp)
                    if original_code is None and full_path.exists():
                        original_code = full_path.read_text(encoding="utf-8")

                    modified_code = modification["modified_code"]

                    if original_code and original_code != modified_code:
                        patch_result = self._apply_diff_to_file(
                            full_path, original_code, modified_code
                        )
                        if patch_result.get("applied"):
                            file_state[fp] = patch_result["result_code"]
                            modification["patch_mode"] = "diff_applied"
                        else:
                            self._write_modification(full_path, modified_code)
                            file_state[fp] = modified_code
                            modification["patch_mode"] = "full_rewrite_fallback"
                    else:
                        self._write_modification(full_path, modified_code)
                        file_state[fp] = modified_code
                        modification["patch_mode"] = "full_rewrite"

                mod_elapsed = (time.time() - mod_start) * 1000
                logger.debug(
                    "Sequential modification for %s completed in %.2fms (patch=%s)",
                    mod.get("target"), mod_elapsed, modification.get("patch_mode", "n/a"),
                )
                results.append(modification)

            except Exception as e:
                logger.error("Sequential modification failed for %s: %s", mod.get("target"), e)
                results.append({
                    "target": mod.get("target"),
                    "file": mod.get("file"),
                    "status": "failed",
                    "error": str(e),
                })

        return results

    def _apply_with_consensus(
        self,
        primary_llm_client,
        mod: Dict[str, Any],
        code_context: str,
        primary_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """对关键修改项冗余执行+共识选择: 2个额外Agent独立生成，ConsensusEngine判断"""
        primary_code = primary_result.get("modified_code", "")
        if not primary_code or primary_result.get("generated_by") != "llm":
            return primary_result

        candidates = [primary_result]
        cheap = CheapLLMClient()

        for attempt_idx in range(2):
            try:
                perspective = "exploratory" if attempt_idx == 0 else "conservative"
                temp = 0.5 if attempt_idx == 0 else 0.2

                alt_result = self._generate_modification_with_client(
                    cheap, mod, code_context,
                    perspective=perspective, temperature_override=temp,
                )
                if alt_result.get("modified_code") and alt_result.get("generated_by") == "llm":
                    alt_result["consensus_agent"] = f"redundant_{attempt_idx}"
                    alt_result["consensus_perspective"] = perspective
                    candidates.append(alt_result)
            except Exception as e:
                logger.debug("Consensus redundant agent %d failed: %s", attempt_idx, e)

        if len(candidates) < 2:
            primary_result["consensus"] = {"status": "insufficient_candidates", "count": len(candidates)}
            return primary_result

        candidate_codes = [c.get("modified_code", "") for c in candidates]
        report = self._consensus_engine.evaluate(
            candidate_codes, task_type="code_modification",
        )

        primary_result["consensus"] = {
            "status": "consensus" if report.has_consensus else "dissent",
            "consensus_ratio": report.consensus_ratio,
            "diversity_score": report.diversity_score,
            "num_candidates": report.total_candidates,
            "num_equivalence_classes": len(report.equivalence_classes),
            "strategy": report.strategy_used,
        }

        if report.has_consensus:
            consensus_code = report.consensus_result
            if consensus_code and consensus_code != primary_code:
                primary_result["modified_code"] = consensus_code
                primary_result["consensus"]["selected"] = "consensus_result"
                logger.info(
                    "[FC2-CONSENSUS] Consensus reached for %s: ratio=%.2f, diversity=%.2f, using consensus version",
                    mod.get("target"), report.consensus_ratio, report.diversity_score,
                )
            else:
                primary_result["consensus"]["selected"] = "primary_matches_consensus"
                logger.info(
                    "[FC2-CONSENSUS] Primary result matches consensus for %s: ratio=%.2f",
                    mod.get("target"), report.consensus_ratio,
                )
        else:
            primary_result["consensus"]["selected"] = "primary_no_consensus"
            primary_result["needs_review"] = True
            primary_result["consensus"]["dissent_previews"] = [
                d["result_preview"][:100] for d in report.dissent_items[:3]
            ]
            logger.warning(
                "[FC2-CONSENSUS] No consensus for %s: ratio=%.2f, diversity=%.2f, %d dissent items, marking for review",
                mod.get("target"), report.consensus_ratio, report.diversity_score,
                len(report.dissent_items),
            )

        return primary_result

    def _apply_diff_to_file(
        self,
        file_path: Path,
        original_code: str,
        modified_code: str,
    ) -> Dict[str, Any]:
        """计算diff并尝试智能合并：如果modified_code包含original_code的大部分，则直接用modified_code；
        否则按unified diff逐行应用"""
        if not original_code or not modified_code:
            return {"applied": False, "reason": "empty code"}

        orig_lines = original_code.splitlines(keepends=True)
        mod_lines = modified_code.splitlines(keepends=True)

        orig_set = set(line.strip() for line in orig_lines if line.strip())
        mod_set = set(line.strip() for line in mod_lines if line.strip())
        if not orig_set:
            return {"applied": False, "reason": "empty original"}

        common = orig_set & mod_set
        overlap_ratio = len(common) / len(orig_set)

        if overlap_ratio >= 0.5:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(modified_code, encoding="utf-8")
                return {"applied": True, "result_code": modified_code, "method": "high_overlap_direct"}
            except Exception as e:
                return {"applied": False, "reason": str(e)}

        diff = difflib.unified_diff(orig_lines, mod_lines, fromfile=str(file_path), tofile=str(file_path) + ".modified", lineterm="")
        diff_text = "\n".join(diff)

        if not any(line.startswith("+") and not line.startswith("++") for line in diff.split("\n")):
            return {"applied": False, "reason": "no_additions_in_diff"}

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(modified_code, encoding="utf-8")
            return {"applied": True, "result_code": modified_code, "method": "diff_apply_fallback"}
        except Exception as e:
            return {"applied": False, "reason": str(e)}

    def _apply_single_modification(
        self,
        mod: Dict[str, Any],
        code_repo_path: str,
        index: int
    ) -> Dict[str, Any]:
        """应用单个修改 - 使用独立LLM客户端"""
        mod_start = time.time()
        llm_client = create_llm_client()

        try:
            file_path = mod.get("file", "")
            full_path = Path(code_repo_path) / file_path

            code_context = ""
            backup_path = None
            if full_path.exists():
                code_context = full_path.read_text(encoding="utf-8")
                # 备份原文件
                backup_path = Path(code_repo_path) / f"{file_path}.bak"
                shutil.copy2(full_path, backup_path)
            else:
                code_context = f"# File not found: {file_path}"

            # 使用LLM生成修改
            modification = self._generate_modification_with_client(llm_client, mod, code_context)
            modification["status"] = "success"
            modification["execution_order"] = index + 1

            # 实际写入修改后的代码
            if modification.get("modified_code") and modification.get("generated_by") == "llm":
                self._write_modification(full_path, modification.get("modified_code", ""))

            mod_elapsed = (time.time() - mod_start) * 1000
            logger.debug(f"[TIMING] Modification {index+1} for {mod.get('target')} completed in {mod_elapsed:.2f}ms")

            return modification

        except Exception as e:
            logger.error(f"Failed to apply modification for {mod.get('target')}: {e}")
            return {
                "target": mod.get("target"),
                "file": mod.get("file"),
                "status": "failed",
                "error": str(e)
            }

    def _generate_modification_with_client(
        self,
        llm_client,
        modification_item: Dict[str, Any],
        code_context: str,
        perspective: str = "",
        temperature_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """使用指定LLM客户端生成修改"""
        target = modification_item.get("target", "")
        file_path = modification_item.get("file", "")
        action = modification_item.get("action", "")

        if llm_client.is_available and code_context and len(code_context) < 20000:
            try:
                max_chars = 8000
                if len(code_context) > max_chars:
                    truncated_code = code_context[:max_chars]
                    last_newline = truncated_code.rfind("\n")
                    if last_newline > max_chars // 2:
                        truncated_code = truncated_code[:last_newline]
                    remaining = len(code_context) - len(truncated_code)
                    truncated_code += f"\n# ... ({remaining} more chars)"
                else:
                    truncated_code = code_context

                perspective_instruction = ""
                if perspective == "exploratory":
                    perspective_instruction = "\n注意：考虑边界情况、异常路径和可扩展性。"
                elif perspective == "conservative":
                    perspective_instruction = "\n注意：最小化改动范围，只修改必要的部分，保持其他代码不变。"

                prompt = f"""你是代码修改专家。根据需求修改以下代码。

修改目标: {target}
文件: {file_path}
修改动作: {action}
{perspective_instruction}
原始代码:
```python
{truncated_code}
```

请输出修改后的完整代码，用```python```包裹。只输出代码，不要解释。"""

                effective_temp = temperature_override if temperature_override is not None else 0.2

                response = llm_client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=effective_temp,
                    max_tokens=4096
                )
                text = llm_client.get_response_text(response)
                if text:
                    modified_code = extract_code_from_llm_response(text, language="python")

                    if modified_code and len(modified_code) >= 10:
                        diff = self._compute_simple_diff(code_context, modified_code)
                        logger.info(f"[LLM] FC2 modification generated for {target}")
                        return {
                            "original_code": code_context[:500],
                            "modified_code": modified_code,
                            "diff": diff,
                            "file_path": file_path,
                            "target": target,
                            "generated_by": "llm"
                        }
            except Exception as e:
                logger.warning(f"[LLM] FC2 modification failed for {target}: {e}")

        # Fallback to template
        return self._generate_modification_template(modification_item, code_context)

    def _generate_modification_template(
        self,
        modification_item: Dict[str, Any],
        code_context: str
    ) -> Dict[str, Any]:
        target = modification_item.get("target", "")
        file_path = modification_item.get("file", "")
        action = modification_item.get("action", "")
        marker = f"# [NeuralAgent] TODO: {action} {target} (fallback - manual review)\n"
        modified_code = marker + code_context if code_context else marker
        return {
            "original_code": code_context[:500] if code_context else "",
            "modified_code": modified_code,
            "diff": f"[FALLBACK] {action} on {target} - marked for manual review",
            "file_path": file_path,
            "target": target,
            "generated_by": "template",
            "requires_manual_review": True,
        }

    def _compute_simple_diff(self, original: str, modified: str) -> str:
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(orig_lines, mod_lines, fromfile="original", tofile="modified", lineterm="")
        return "\n".join(diff)

    def _write_modification(self, file_path: Path, modified_code: str):
        """写入修改后的代码到文件"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(modified_code, encoding="utf-8")
            logger.info(f"[FC2] Written modified code to {file_path}")
        except Exception as e:
            logger.error(f"Failed to write modified code to {file_path}: {e}")

    def verify_syntax(self, modification_result: Dict[str, Any]) -> bool:
        """验证语法正确性：Python用ast.parse+compile, 其他语言用tree-sitter"""
        code = modification_result.get("modified_code", "")
        file_path = modification_result.get("file_path", "") or modification_result.get("file", "")
        if not code:
            return False

        if file_path.endswith(".py"):
            try:
                compile(code, file_path or "<string>", "exec")
                return True
            except SyntaxError as e:
                logger.warning("[FC2-SYNTAX] Python syntax error in %s: %s", file_path, e)
                return False

        suffix = Path(file_path).suffix.lower() if file_path else ""
        if suffix and suffix != ".py":
            try:
                from app.services.fullconnect.smart_context import SmartContextWindow, TREE_SITTER_AVAILABLE
                if TREE_SITTER_AVAILABLE:
                    ts_parsers = SmartContextWindow._get_ts_parsers()
                    parser = ts_parsers.get(suffix)
                    if parser:
                        tree = parser.parse(bytes(code, "utf-8"))
                        if not tree.root_node.has_error:
                            return True
                        logger.warning("[FC2-SYNTAX] Tree-sitter parse error in %s", file_path)
                        return False
            except Exception:
                pass

        return True

    @staticmethod
    def _check_modification_integrity(
        modifications: List[Dict[str, Any]],
        fc1_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """完整性校验：验证FC1的每个(file,target)在FC2结果中都有对应记录"""
        fc1_mods = fc1_output.get("solution", {}).get("modification_list", [])
        fc1_targets = set()
        for m in fc1_mods:
            fp = m.get("file", "")
            target = m.get("target", "")
            if fp and target:
                fc1_targets.add((fp, target))

        fc2_covered = set()
        for m in modifications:
            fp = m.get("file_path", "") or m.get("file", "")
            target = m.get("target", "")
            if fp and target:
                fc2_covered.add((fp, target))

        missing = fc1_targets - fc2_covered
        conflict_count = sum(1 for m in modifications if m.get("conflict"))
        merge_conflicts = fc1_output.get("solution", {}).get("merge_conflicts", {})

        return {
            "fc1_targets": len(fc1_targets),
            "fc2_covered": len(fc2_covered & fc1_targets),
            "missing_targets": len(missing),
            "missing_list": [{"file": f, "target": t} for f, t in sorted(missing)[:20]],
            "conflict_modifications": conflict_count,
            "merge_conflicts_from_fc1": merge_conflicts,
        }

    def _run_pytest_validation(self, code_repo_path: str) -> Optional[Dict[str, Any]]:
        """运行pytest验证修改后的代码"""
        repo_path = Path(code_repo_path)
        test_dirs = list(repo_path.rglob("tests")) + list(repo_path.rglob("test"))
        if not test_dirs:
            return None

        pytest_candidates = []
        for d in test_dirs:
            if d.is_dir() and any(f.suffix == ".py" for f in d.iterdir() if f.is_file()):
                pytest_candidates.append(d)
        if not pytest_candidates:
            return None

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", str(pytest_candidates[0]), "--tb=short", "-q", "--no-header"],
                capture_output=True, text=True, timeout=60, cwd=str(repo_path),
            )
            passed = result.returncode == 0
            stdout_last = result.stdout[-500:] if result.stdout else ""
            stderr_last = result.stderr[-500:] if result.stderr else ""
            test_result = {
                "pytest_passed": passed,
                "returncode": result.returncode,
                "output_tail": stdout_last,
            }
            if not passed:
                test_result["error_tail"] = stderr_last
            logger.info("[FC2-PYTEST] pytest result: passed=%s, rc=%d", passed, result.returncode)
            return test_result
        except subprocess.TimeoutExpired:
            logger.warning("[FC2-PYTEST] pytest timed out after 60s")
            return {"pytest_passed": False, "error": "timeout"}
        except FileNotFoundError:
            logger.debug("[FC2-PYTEST] pytest not available")
            return None
        except Exception as e:
            logger.warning("[FC2-PYTEST] pytest execution failed: %s", e)
            return None

    @staticmethod
    def _rollback_failed_files(code_repo_path: str, failed_files: List[str]) -> List[str]:
        """从.bak文件回滚失败的修改"""
        rolled_back = []
        repo_path = Path(code_repo_path)
        for fp in failed_files:
            full_path = repo_path / fp
            backup_path = repo_path / f"{fp}.bak"
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, full_path)
                    rolled_back.append(fp)
                    logger.info("[FC2-ROLLBACK] Restored %s from backup", fp)
                except Exception as e:
                    logger.error("[FC2-ROLLBACK] Failed to restore %s: %s", fp, e)
        return rolled_back

    def create_fc2_output(
        self,
        modifications: List[Dict[str, Any]],
        fc1_output: Dict[str, Any],
        task_id: str
    ) -> Dict[str, Any]:
        """创建全连接层2输出"""
        successful = [m for m in modifications if m.get("status") == "success"]
        failed = [m for m in modifications if m.get("status") == "failed"]

        output = {
            "task_id": task_id,
            "layer": "code_generation",
            "layer_name": "full_connect_2",
            "summary": {
                "total_modifications": len(modifications),
                "successful": len(successful),
                "failed": len(failed)
            },
            "modifications": modifications,
            "fc1_reference": {
                "solution_overview": fc1_output.get("solution", {}).get("overview", "")
            },
            "integrity_check": self._check_modification_integrity(modifications, fc1_output),
            "created_at": datetime.now().isoformat()
        }

        return output

    def process_task(
        self,
        task_id: str,
        fc1_output: Dict[str, Any],
        code_repo_path: str
    ) -> Dict[str, Any]:
        """处理任务 - 执行完整的代码生成层流程"""
        start_time = time.time()
        logger.info(f"[START] FC2 Code Generation layer processing task {task_id}")

        # 获取修改清单
        modification_list = fc1_output.get("solution", {}).get("modification_list", [])

        # 1. 基于信任度过滤
        filtered_mods = self.filter_by_trust(modification_list, agent_id="fc1_agent")

        # 2. 应用修改
        modifications = self.apply_modifications(filtered_mods, code_repo_path)

        # 3. 验证语法
        syntax_failed_files = []
        for mod in modifications:
            if mod.get("status") == "success":
                mod["syntax_valid"] = self.verify_syntax(mod)
                if not mod.get("syntax_valid"):
                    syntax_failed_files.append(mod.get("file_path", "") or mod.get("file", ""))

        # 4. 运行pytest验证（如有测试目录）
        test_result = self._run_pytest_validation(code_repo_path)

        # 5. 语法失败或测试失败时回滚
        rollback_files = []
        if syntax_failed_files:
            logger.warning("[FC2] Syntax validation failed for %d files, rolling back", len(syntax_failed_files))
            rollback_files = self._rollback_failed_files(code_repo_path, syntax_failed_files)

        # 6. 创建输出
        output = self.create_fc2_output(modifications, fc1_output, task_id)
        if test_result:
            output["test_validation"] = test_result
        if rollback_files:
            output["rolled_back_files"] = rollback_files

        # 7. 保存输出
        save_layer_output(task_id, "code_generation", output, "modifications.json")

        total_elapsed = (time.time() - start_time) * 1000
        logger.info(f"[COMPLETE] FC2 layer completed for task {task_id} in {total_elapsed:.2f}ms")

        return output


# Singleton instance
_code_generation_service: Optional[CodeGenerationService] = None


def get_code_generation_service() -> CodeGenerationService:
    """获取代码生成服务实例"""
    global _code_generation_service
    if _code_generation_service is None:
        _code_generation_service = CodeGenerationService()
    return _code_generation_service