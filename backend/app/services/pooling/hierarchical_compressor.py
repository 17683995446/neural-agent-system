"""
HierarchicalCompressor — 三级压缩
L1 - 模块摘要(全部保留, 每模块~50字)  → 100模块 = 5000字 ≈ 2000 tokens
L2 - 文件摘要(相关模块, 每文件签名列表) → 200文件 = ~15000字 ≈ 6000 tokens
L3 - 函数详情(最相关, 完整签名+docstr)  → 50函数 = ~10000字 ≈ 4000 tokens
总计: ~12000 tokens, 在LLM上下文窗口内
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging import logger


@dataclass
class CompressedOutput:
    module_summaries: List[Dict[str, Any]] = field(default_factory=list)
    file_summaries: List[Dict[str, Any]] = field(default_factory=list)
    function_details: List[Dict[str, Any]] = field(default_factory=list)
    total_modules: int = 0
    total_files_scanned: int = 0
    total_functions_scanned: int = 0


class HierarchicalCompressor:
    def __init__(
        self,
        max_module_summaries: int = 100,
        max_file_summaries: int = 200,
        max_function_details: int = 50,
    ):
        self.max_module_summaries = max_module_summaries
        self.max_file_summaries = max_file_summaries
        self.max_function_details = max_function_details

    def compress(
        self,
        analysis_results: List[Dict],
        user_requirement: str = "",
        modules: Optional[List] = None,
    ) -> CompressedOutput:
        output = CompressedOutput()
        output.total_files_scanned = len(analysis_results)

        if modules:
            for mod in modules[: self.max_module_summaries]:
                output.module_summaries.append({
                    "name": mod.name,
                    "file_count": mod.file_count,
                    "dependencies": list(mod.dependencies)[:5],
                    "summary": self._summarize_module(mod, analysis_results),
                })
        else:
            dir_groups = self._group_by_directory(analysis_results)
            for dir_name, files in list(dir_groups.items())[: self.max_module_summaries]:
                output.module_summaries.append({
                    "name": dir_name,
                    "file_count": len(files),
                    "summary": f"{len(files)} files",
                })
        output.total_modules = len(output.module_summaries)

        scored_files = self._score_and_sort_files(analysis_results, user_requirement)
        for item in scored_files[: self.max_file_summaries]:
            output.file_summaries.append({
                "file_path": item.get("file_path", ""),
                "functions": [f.get("name", "") for f in item.get("functions", [])],
                "classes": [c.get("name", "") for c in item.get("classes", [])],
                "summary": item.get("summary", ""),
                "relevance": item.get("_relevance", 0),
            })

        top_functions = self._extract_top_functions(
            scored_files[: self.max_file_summaries],
            limit=self.max_function_details,
        )
        for func in top_functions:
            output.function_details.append(func)

        output.total_functions_scanned = sum(
            len(r.get("functions", [])) for r in analysis_results
        )

        logger.info(
            f"HierarchicalCompressor: {output.total_modules} modules, "
            f"{len(output.file_summaries)} files, "
            f"{len(output.function_details)} functions"
        )
        return output

    def _summarize_module(self, module: Any, analysis_results: List[Dict]) -> str:
        mod_files = [
            r for r in analysis_results
            if any(str(f) in r.get("file_path", "") for f in module.files[:20])
        ]
        total_funcs = sum(len(r.get("functions", [])) for r in mod_files)
        total_classes = sum(len(r.get("classes", [])) for r in mod_files)
        return f"{len(mod_files)} files, {total_funcs} functions, {total_classes} classes"

    @staticmethod
    def _group_by_directory(results: List[Dict]) -> Dict[str, List]:
        groups: Dict[str, List] = {}
        for r in results:
            fp = r.get("file_path", "")
            parts = Path(fp).parts
            dir_name = "/".join(parts[:2]) if len(parts) > 1 else "root"
            groups.setdefault(dir_name, []).append(r)
        return groups

    @staticmethod
    def _score_and_sort_files(results: List[Dict], requirement: str) -> List[Dict]:
        keywords = set(re.findall(r"[a-zA-Z_]{3,}", requirement.lower())) if requirement else set()

        for r in results:
            score = 0.0
            fp = r.get("file_path", "").lower()
            for kw in keywords:
                if kw in fp:
                    score += 0.3
                for func in r.get("functions", []):
                    if kw in func.get("name", "").lower():
                        score += 0.2
                for cls in r.get("classes", []):
                    if kw in cls.get("name", "").lower():
                        score += 0.2
            r["_relevance"] = score

        return sorted(results, key=lambda x: x.get("_relevance", 0), reverse=True)

    @staticmethod
    def _extract_top_functions(files: List[Dict], limit: int) -> List[Dict]:
        functions: List[Dict] = []
        for f in files:
            for func in f.get("functions", []):
                functions.append({
                    "name": func.get("name", ""),
                    "file_path": f.get("file_path", ""),
                    "line": func.get("line") or func.get("start_line"),
                    "class": func.get("class_name", ""),
                    "relevance": f.get("_relevance", 0),
                })

        functions.sort(key=lambda x: x["relevance"], reverse=True)
        return functions[:limit]
