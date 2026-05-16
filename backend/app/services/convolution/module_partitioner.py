"""
ModulePartitioner — 项目自动拆模块策略
1. 按目录结构拆分(src/api, src/core等)
2. 按依赖图合并小模块 (基于AST imports)
3. 按文件数上限拆分大模块(每模块<=200文件)
4. 需求路由: 仅分析需求相关的模块
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from app.core.logging import logger

try:
    from app.services.convolution.service import CodeAnalyzer
    _CODE_ANALYZER_AVAILABLE = True
except Exception:
    _CODE_ANALYZER_AVAILABLE = False


@dataclass
class Module:
    name: str
    root: Path
    files: List[Path] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)
    entry_points: List[Path] = field(default_factory=list)
    file_count: int = 0
    total_lines: int = 0


_EXCLUDED_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", "env", ".env", ".cache",
}

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
    ".go", ".rs", ".cpp", ".c", ".h", ".hpp",
    ".rb", ".php", ".cs", ".swift", ".kt",
}


class ModulePartitioner:
    MAX_FILES_PER_MODULE = 200
    MIN_FILES_PER_MODULE = 5

    def __init__(self):
        self._code_analyzer: Optional[CodeAnalyzer] = None

    def _get_analyzer(self) -> Optional[CodeAnalyzer]:
        if self._code_analyzer is not None:
            return self._code_analyzer
        if _CODE_ANALYZER_AVAILABLE:
            try:
                self._code_analyzer = CodeAnalyzer()
                return self._code_analyzer
            except Exception:
                pass
        return None

    def partition(self, project_root: Path) -> List[Module]:
        modules = self._partition_by_directory(project_root)
        self._analyze_dependencies(modules)
        modules = self._merge_small_modules(modules)
        modules = self._split_large_modules(modules)
        logger.info(
            f"ModulePartitioner: partitioned {project_root} into {len(modules)} modules"
        )
        return modules

    def _is_excluded_dir(self, d: Path) -> bool:
        return d.name in _EXCLUDED_DIRS or d.name.startswith(".")

    def _is_excluded(self, f: Path) -> bool:
        parts = f.parts
        return any(p in _EXCLUDED_DIRS for p in parts)

    def _partition_by_directory(self, root: Path) -> List[Module]:
        modules = []
        try:
            subdirs = [d for d in root.iterdir() if d.is_dir() and not self._is_excluded_dir(d)]
        except OSError:
            return modules

        for subdir in subdirs:
            files = [
                f for f in subdir.rglob("*")
                if f.is_file() and f.suffix in _CODE_EXTENSIONS and not self._is_excluded(f)
            ]
            if len(files) >= self.MIN_FILES_PER_MODULE:
                modules.append(Module(
                    name=subdir.name,
                    root=subdir,
                    files=files,
                    file_count=len(files),
                ))

        try:
            root_files = [
                f for f in root.glob("*")
                if f.is_file() and f.suffix in _CODE_EXTENSIONS
            ]
        except OSError:
            root_files = []
        if root_files:
            modules.append(Module(
                name="root", root=root, files=root_files, file_count=len(root_files)
            ))

        return modules

    def _analyze_dependencies(self, modules: List[Module]):
        module_file_map: dict = {}
        for mod in modules:
            for f in mod.files:
                try:
                    module_file_map[f.resolve()] = mod.name
                except OSError:
                    pass

        analyzer = self._get_analyzer()

        for mod in modules:
            for f in mod.files:
                imports = []
                if analyzer and f.suffix in analyzer.SUPPORTED_LANGUAGES:
                    try:
                        result = analyzer.parse_file(str(f))
                        imports = result.get("imports", [])
                    except Exception:
                        pass
                if not imports:
                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")[:5000]
                        for line in content.split("\n"):
                            stripped = line.strip()
                            if stripped.startswith(("import ", "from ", "use ", "#include", "require")):
                                imports.append(stripped)
                    except Exception:
                        pass

                for imp in imports:
                    for other_mod in modules:
                        if other_mod.name != mod.name and other_mod.name in imp:
                            mod.dependencies.add(other_mod.name)

    def _merge_small_modules(self, modules: List[Module]) -> List[Module]:
        small = [m for m in modules if m.file_count < self.MIN_FILES_PER_MODULE]
        large = [m for m in modules if m.file_count >= self.MIN_FILES_PER_MODULE]

        for s in small:
            target = None
            for dep_name in s.dependencies:
                target = next((m for m in large if m.name == dep_name), None)
                if target:
                    break
            if target:
                target.files.extend(s.files)
                target.file_count += s.file_count
            else:
                large.append(s)

        return large

    def _split_large_modules(self, modules: List[Module]) -> List[Module]:
        result = []
        for mod in modules:
            if mod.file_count <= self.MAX_FILES_PER_MODULE:
                result.append(mod)
                continue

            subdirs = set()
            for f in mod.files:
                try:
                    rel = f.parent.relative_to(mod.root)
                    if len(rel.parts) > 0:
                        subdirs.add(rel.parts[0])
                except ValueError:
                    pass

            for subdir_name in subdirs:
                sub_files = [
                    f for f in mod.files
                    if self._get_first_subdir(f, mod.root) == subdir_name
                ]
                if sub_files:
                    result.append(Module(
                        name=f"{mod.name}/{subdir_name}",
                        root=mod.root / subdir_name,
                        files=sub_files,
                        file_count=len(sub_files),
                    ))

            remaining = [
                f for f in mod.files
                if self._get_first_subdir(f, mod.root) is None
            ]
            if remaining:
                result.append(Module(
                    name=mod.name, root=mod.root, files=remaining, file_count=len(remaining)
                ))

        return result

    @staticmethod
    def _get_first_subdir(f: Path, mod_root: Path) -> str | None:
        try:
            rel = f.parent.relative_to(mod_root)
            return rel.parts[0] if len(rel.parts) > 0 else None
        except ValueError:
            return None

    def route_requirement(
        self, requirement: str, modules: List[Module], top_k: int = 5
    ) -> List[Module]:
        keywords = set(re.findall(r"[a-zA-Z_]{3,}", requirement.lower()))

        scored = []
        for mod in modules:
            score = 0.0
            for kw in keywords:
                if kw in mod.name.lower():
                    score += 1.0
            for f in mod.files[:20]:
                for kw in keywords:
                    if kw in f.stem.lower():
                        score += 0.5
            scored.append((score, mod))

        scored.sort(key=lambda x: x[0], reverse=True)

        selected: set[str] = set()
        for score, mod in scored:
            if len(selected) >= top_k:
                break
            if score > 0:
                selected.add(mod.name)
                for dep in mod.dependencies:
                    selected.add(dep)

        if not selected:
            for _, mod in scored[:top_k]:
                selected.add(mod.name)

        return [m for m in modules if m.name in selected]
