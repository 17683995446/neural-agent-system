"""
ModificationDependencyGraph — 修改依赖图
1. 同一文件的修改 → 串行(按行号排序)
2. 文件A import/调用文件B的符号 → B先改
3. 无依赖的修改 → 可并行

输出: 分层执行计划 List[List[Mod]]
- 外层: 串行批次
- 内层: 同批次可并行
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from app.core.logging import logger


class ModificationDependencyGraph:
    def __init__(self, code_index=None):
        self._code_index = code_index

    def build_execution_plan(
        self, modifications: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        file_groups: Dict[str, List[Dict]] = defaultdict(list)
        for mod in modifications:
            fp = mod.get("file", "")
            file_groups[fp].append(mod)

        for fp, mods in file_groups.items():
            mods.sort(key=lambda m: m.get("line") or 0)

        file_deps = self._build_file_dependencies(file_groups)
        sorted_files = self._topological_sort(list(file_groups.keys()), file_deps)

        plan: List[List[Dict]] = []
        processed_files: Set[str] = set()
        remaining = set(sorted_files)

        while remaining:
            batch_files = []
            for fp in sorted(remaining):
                deps = file_deps.get(fp, set())
                if deps.issubset(processed_files):
                    batch_files.append(fp)

            if not batch_files:
                batch_files = list(remaining)[:1]

            parallel_mods = []
            for fp in batch_files:
                for mod in file_groups[fp]:
                    parallel_mods.append({**mod, "_sequential_group": fp})

            plan.append(parallel_mods)

            for fp in batch_files:
                remaining.discard(fp)
                processed_files.add(fp)

        logger.info(
            "ModificationDependencyGraph: %d modifications → %d execution batches",
            len(modifications), len(plan),
        )
        return plan

    def _build_file_dependencies(
        self,
        file_groups: Dict[str, List[Dict]],
    ) -> Dict[str, Set[str]]:
        """跨文件依赖检测：使用CodeStructureIndex调用图或import关系"""
        deps: Dict[str, Set[str]] = defaultdict(set)
        target_to_file: Dict[str, str] = {}
        for fp, mods in file_groups.items():
            for mod in mods:
                target = mod.get("target", "")
                if target:
                    target_to_file[target] = fp

        if self._code_index is not None:
            for fp, mods in file_groups.items():
                for mod in mods:
                    target = mod.get("target", "")
                    if not target:
                        continue
                    callers = self._code_index.query_callers_of(target)
                    for caller in callers:
                        caller_file = caller.get("caller_file", "")
                        if caller_file in file_groups and caller_file != fp:
                            deps[caller_file].add(fp)
                    import_refs = self._code_index.query_files_by_import(target)
                    for ref_file in import_refs:
                        if ref_file in file_groups and ref_file != fp:
                            deps[ref_file].add(fp)
        else:
            for fp, mods in file_groups.items():
                for mod in mods:
                    target = mod.get("target", "")
                    if not target:
                        continue
                    for other_fp, other_mods in file_groups.items():
                        if other_fp != fp:
                            for other_mod in other_mods:
                                other_depends = other_mod.get("depends_on", [])
                                if target in other_depends:
                                    deps[other_fp].add(fp)

        return deps

    @staticmethod
    def _topological_sort(
        files: List[str], deps: Dict[str, Set[str]]
    ) -> List[str]:
        visited: Set[str] = set()
        result: List[str] = []
        visiting: Set[str] = set()

        def visit(f: str):
            if f in visited:
                return
            if f in visiting:
                return
            visiting.add(f)
            for dep in deps.get(f, set()):
                if dep in set(files):
                    visit(dep)
            visiting.discard(f)
            visited.add(f)
            result.append(f)

        for f in files:
            visit(f)

        return result

    @staticmethod
    def get_sequential_groups(batch: List[Dict]) -> Dict[str, List[Dict]]:
        groups: Dict[str, List[Dict]] = defaultdict(list)
        for mod in batch:
            group_key = mod.get("_sequential_group", mod.get("file", ""))
            groups[group_key].append(mod)
        return groups
