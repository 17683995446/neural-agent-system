"""
ChangeDetector — 增量变更检测
1. 文件级: hash比较 → 找出新增/修改/删除
2. 符号级: AST diff → 找出修改的函数/类 (多语言: Python ast + Tree-sitter)
3. 影响级: 调用链分析 → 标记受影响的函数
"""
import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.core.logging import logger
from app.core.safe_pickle import safe_dump_to_file, safe_load_from_file

try:
    from tree_sitter import Language, Parser

    import tree_sitter_python as _ts_python
    import tree_sitter_javascript as _ts_javascript
    import tree_sitter_typescript as _ts_typescript
    import tree_sitter_java as _ts_java
    import tree_sitter_go as _ts_go
    import tree_sitter_rust as _ts_rust
    import tree_sitter_c as _ts_c
    import tree_sitter_cpp as _ts_cpp
    import tree_sitter_ruby as _ts_ruby

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


@dataclass
class ChangeSet:
    changed_files: List[Path] = field(default_factory=list)
    changed_symbols: List[str] = field(default_factory=list)
    affected_symbols: List[str] = field(default_factory=list)
    unchanged_files: List[Path] = field(default_factory=list)
    total_files: int = 0
    change_ratio: float = 0.0


_DEFAULT_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".cpp", ".c"}

_EXCLUDED_PATTERNS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}


class ChangeDetector:
    def __init__(self, cache_dir: str = ".cache/changes"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._file_hashes: Dict[str, str] = {}
        self._symbol_index: Dict[str, Set[str]] = {}
        self._call_graph: Dict[str, Set[str]] = {}
        self._ts_parsers: Optional[Dict[str, Parser]] = None
        self._load_cache()

    def _init_ts_parsers(self) -> Dict[str, Parser]:
        """初始化Tree-sitter多语言解析器（懒加载）"""
        if self._ts_parsers is not None:
            return self._ts_parsers

        if not TREE_SITTER_AVAILABLE:
            self._ts_parsers = {}
            return self._ts_parsers

        language_map = {
            ".js": lambda: Language(_ts_javascript.language()),
            ".jsx": lambda: Language(_ts_javascript.language()),
            ".ts": lambda: Language(_ts_typescript.language_typescript()),
            ".tsx": lambda: Language(_ts_typescript.language_tsx()),
            ".java": lambda: Language(_ts_java.language()),
            ".go": lambda: Language(_ts_go.language()),
            ".rs": lambda: Language(_ts_rust.language()),
            ".c": lambda: Language(_ts_c.language()),
            ".h": lambda: Language(_ts_c.language()),
            ".cpp": lambda: Language(_ts_cpp.language()),
            ".hpp": lambda: Language(_ts_cpp.language()),
            ".rb": lambda: Language(_ts_ruby.language()),
        }

        parsers = {}
        for ext, builder in language_map.items():
            try:
                lang = builder()
                parsers[ext] = Parser(lang)
            except Exception as e:
                logger.debug(f"ChangeDetector: failed to init parser for {ext}: {e}")

        self._ts_parsers = parsers
        logger.info(f"ChangeDetector: tree-sitter initialized with {len(parsers)} parsers")
        return self._ts_parsers

    @staticmethod
    def _hash_file(path: Path) -> str:
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()

    def detect_changes(
        self,
        project_root: Path,
        code_extensions: set | None = None,
    ) -> ChangeSet:
        if code_extensions is None:
            code_extensions = _DEFAULT_EXTENSIONS

        all_files: List[Path] = []
        for ext in code_extensions:
            for f in project_root.rglob(f"*{ext}"):
                if f.is_file() and not any(p in str(f) for p in _EXCLUDED_PATTERNS):
                    all_files.append(f)

        changed: List[Path] = []
        unchanged: List[Path] = []

        for f in all_files:
            try:
                key = str(f.relative_to(project_root))
            except ValueError:
                key = str(f)
            try:
                current_hash = self._hash_file(f)
            except OSError:
                continue
            previous_hash = self._file_hashes.get(key)

            if previous_hash is None or current_hash != previous_hash:
                changed.append(f)
                self._file_hashes[key] = current_hash
            else:
                unchanged.append(f)

        changed_symbols = self._analyze_changed_symbols(changed)
        self._build_call_graph(all_files, changed_files=changed if changed else None)
        affected_symbols = self._propagate_effects(changed_symbols)

        change_set = ChangeSet(
            changed_files=changed,
            changed_symbols=changed_symbols,
            affected_symbols=affected_symbols,
            unchanged_files=unchanged,
            total_files=len(all_files),
            change_ratio=len(changed) / max(len(all_files), 1),
        )

        self._save_cache()
        logger.info(
            f"ChangeDetector: {len(changed)}/{len(all_files)} files changed "
            f"({change_set.change_ratio:.1%}), "
            f"call_graph edges={sum(len(v) for v in self._call_graph.values())}"
        )
        return change_set

    def _analyze_changed_symbols(self, changed_files: List[Path]) -> List[str]:
        """多语言符号级变更检测：Python用ast，其他语言用Tree-sitter"""
        symbols: List[str] = []
        ts_parsers = None

        for f in changed_files:
            try:
                if f.suffix == ".py":
                    tree = ast.parse(f.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            symbols.append(f"{f}:{node.name}")
                        elif isinstance(node, ast.ClassDef):
                            symbols.append(f"{f}:{node.name}")
                elif f.suffix != ".py" and TREE_SITTER_AVAILABLE:
                    if ts_parsers is None:
                        ts_parsers = self._init_ts_parsers()
                    parser = ts_parsers.get(f.suffix.lower())
                    if parser:
                        ts_tree = parser.parse(f.read_bytes())
                        func_types = {
                            "function_definition", "function_declaration",
                            "function_item", "method_definition",
                            "method_declaration", "method",
                            "arrow_function",
                        }
                        class_types = {
                            "class_definition", "class_declaration",
                            "class", "struct_item", "interface_declaration",
                            "enum_declaration", "enum_item",
                            "type_declaration", "trait_item",
                        }

                        def _ts_traverse(node):
                            for child in node.children:
                                if child.type in func_types or child.type in class_types:
                                    name = ""
                                    for c in child.children:
                                        if c.type in ("identifier", "name", "type_identifier", "property_identifier", "constant"):
                                            name = c.text.decode("utf-8") if isinstance(c.text, bytes) else str(c.text)
                                            break
                                    if name:
                                        symbols.append(f"{f}:{name}")
                                _ts_traverse(child)

                        _ts_traverse(ts_tree.root_node)
            except Exception:
                pass
        return symbols

    def _build_call_graph(self, all_files: List[Path], changed_files: Optional[List[Path]] = None):
        """调用图构建：首次全量，后续增量（仅重建changed文件的边）"""
        ts_parsers = None
        files_to_process = changed_files if changed_files and self._call_graph else all_files
        is_full_build = not self._call_graph or changed_files is None

        if is_full_build:
            self._call_graph.clear()
            self._symbol_index.clear()

        if is_full_build:
            file_prefix_set: Optional[Set[str]] = None
        else:
            file_prefix_set = {str(f) for f in files_to_process}
            keys_to_remove = [k for k in self._call_graph if any(k.startswith(pfx) for pfx in file_prefix_set)]
            for k in keys_to_remove:
                del self._call_graph[k]

        for f in files_to_process:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if f.suffix == ".py":
                self._build_call_graph_python(f, content, file_prefix_set)
            elif TREE_SITTER_AVAILABLE:
                if ts_parsers is None:
                    ts_parsers = self._init_ts_parsers()
                parser = ts_parsers.get(f.suffix.lower())
                if parser:
                    self._build_call_graph_tree_sitter(f, content, parser, file_prefix_set)

    def _build_call_graph_python(self, file_path: Path, content: str, _file_prefix_set: Optional[Set[str]] = None):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        file_key = str(file_path)
        file_symbols: Set[str] = set()
        for node in ast.walk(tree):
            name = getattr(node, "name", None)
            if name and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                file_symbols.add(f"{file_key}:{name}")

        self._symbol_index[file_key] = file_symbols

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = f"{file_key}:{node.name}"
                callees: Set[str] = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        callee_name = None
                        if isinstance(child.func, ast.Name):
                            callee_name = child.func.id
                        elif isinstance(child.func, ast.Attribute):
                            callee_name = child.func.attr
                        if callee_name:
                            callees.add(f"{file_key}:{callee_name}")
                if callees:
                    self._call_graph[caller] = callees

    def _build_call_graph_tree_sitter(self, file_path: Path, content: str, parser, _file_prefix_set: Optional[Set[str]] = None):
        tree = parser.parse(bytes(content, "utf-8"))
        file_key = str(file_path)

        func_types = {
            "function_definition", "function_declaration",
            "function_item", "function_signature_item",
            "method_definition", "method_declaration",
            "method", "arrow_function",
            "generator_function_declaration", "constructor_definition",
        }
        call_types = {"call_expression", "function_call"}
        name_types = ("identifier", "name", "property_identifier", "type_identifier", "field_identifier", "constant")

        file_symbols: Set[str] = set()

        def _node_name(node):
            for child in node.children:
                if child.type in name_types:
                    text = child.text
                    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
            return ""

        def _collect_symbols(node):
            if node.type in func_types:
                name = _node_name(node)
                if name:
                    file_symbols.add(f"{file_key}:{name}")
            for child in node.children:
                _collect_symbols(child)

        _collect_symbols(tree.root_node)
        self._symbol_index[file_key] = file_symbols

        def _extract_calls(func_node):
            callees: Set[str] = set()
            def _walk(n):
                if n.type in call_types:
                    for child in n.children:
                        if child.type in name_types:
                            text = child.text
                            callee_name = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                            callees.add(f"{file_key}:{callee_name}")
                            break
                for child in n.children:
                    if child.type not in func_types:
                        _walk(child)
            _walk(func_node)
            return callees

        def _build_edges(node):
            if node.type in func_types:
                name = _node_name(node)
                if name:
                    caller = f"{file_key}:{name}"
                    callees = _extract_calls(node)
                    if callees:
                        self._call_graph[caller] = callees
            for child in node.children:
                _build_edges(child)

        _build_edges(tree.root_node)

    def _propagate_effects(self, changed_symbols: List[str]) -> List[str]:
        affected: Set[str] = set()
        for sym in changed_symbols:
            for caller, callees in self._call_graph.items():
                if sym in callees:
                    affected.add(caller)
        return list(affected)

    def _load_cache(self):
        cache_file = self._cache_dir / "change_cache.pkl"
        data = safe_load_from_file(cache_file)
        if data is not None:
            self._file_hashes = data.get("hashes", {})
            self._symbol_index = data.get("symbols", {})
            self._call_graph = data.get("call_graph", {})

    def _save_cache(self):
        cache_file = self._cache_dir / "change_cache.pkl"
        data = {
            "hashes": self._file_hashes,
            "symbols": self._symbol_index,
            "call_graph": self._call_graph,
        }
        safe_dump_to_file(data, cache_file)
