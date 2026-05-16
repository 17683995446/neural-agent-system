"""
CodeStructureIndex — 项目级代码结构持久化索引 (SQLite)
首次全量扫描构建，后续增量更新
存储：符号表(函数/类/方法)、调用图边、文件依赖(import关系)、文件hash
供所有层快速检索，避免重复AST解析
"""
import ast
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.logging import logger

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


_EXCLUDED = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}

_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
    ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".rb",
}


class CodeStructureIndex:
    def __init__(self, db_path: str = ".cache/code_index.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._ts_parsers: Optional[Dict[str, Parser]] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                file_path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                language TEXT NOT NULL,
                line_count INTEGER NOT NULL DEFAULT 0,
                last_indexed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                signature TEXT DEFAULT '',
                docstring TEXT DEFAULT '',
                FOREIGN KEY (file_path) REFERENCES files(file_path)
            );

            CREATE TABLE IF NOT EXISTS call_edges (
                caller_file TEXT NOT NULL,
                caller_name TEXT NOT NULL,
                callee_file TEXT NOT NULL,
                callee_name TEXT NOT NULL,
                PRIMARY KEY (caller_file, caller_name, callee_file, callee_name)
            );

            CREATE TABLE IF NOT EXISTS imports (
                file_path TEXT NOT NULL,
                import_text TEXT NOT NULL,
                imported_symbol TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                PRIMARY KEY (file_path, import_text)
            );

            CREATE TABLE IF NOT EXISTS inheritance (
                file_path TEXT NOT NULL,
                class_name TEXT NOT NULL,
                parent_name TEXT NOT NULL,
                parent_file TEXT DEFAULT '',
                PRIMARY KEY (file_path, class_name, parent_name)
            );

            CREATE TABLE IF NOT EXISTS decorators (
                file_path TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                decorator_name TEXT NOT NULL,
                decorator_args TEXT DEFAULT '',
                PRIMARY KEY (file_path, symbol_name, decorator_name)
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
            CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
            CREATE INDEX IF NOT EXISTS idx_call_edges_caller ON call_edges(caller_file, caller_name);
            CREATE INDEX IF NOT EXISTS idx_call_edges_callee ON call_edges(callee_file, callee_name);
            CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_path);
            CREATE INDEX IF NOT EXISTS idx_imports_symbol ON imports(imported_symbol);
            CREATE INDEX IF NOT EXISTS idx_inheritance_class ON inheritance(file_path, class_name);
            CREATE INDEX IF NOT EXISTS idx_inheritance_parent ON inheritance(parent_name);
            CREATE INDEX IF NOT EXISTS idx_decorators_symbol ON decorators(file_path, symbol_name);
            CREATE INDEX IF NOT EXISTS idx_decorators_name ON decorators(decorator_name);
        """)
        conn.commit()

    def _init_ts_parsers(self) -> Dict[str, Parser]:
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
            except Exception:
                pass
        self._ts_parsers = parsers
        return parsers

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _detect_language(suffix: str) -> str:
        mapping = {
            ".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "typescript",
            ".java": "java", ".go": "go", ".rs": "rust",
            ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
            ".rb": "ruby",
        }
        return mapping.get(suffix, "unknown")

    def build_index(self, project_root: Path, force_full: bool = False) -> Dict[str, Any]:
        """构建/更新索引：首次全量，后续增量"""
        all_files = []
        for ext in _CODE_EXTENSIONS:
            for f in project_root.rglob(f"*{ext}"):
                if f.is_file() and not any(p in str(f) for p in _EXCLUDED):
                    all_files.append(f)

        conn = self._get_conn()
        if force_full:
            changed_files = all_files
        else:
            changed_files = []
            for f in all_files:
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                content_hash = self._hash_content(content)
                row = conn.execute(
                    "SELECT content_hash FROM files WHERE file_path=?",
                    (str(f),),
                ).fetchone()
                if row is None or row["content_hash"] != content_hash:
                    changed_files.append(f)

        if not changed_files:
            stats = self.get_stats()
            logger.info("CodeStructureIndex: no changes, index up-to-date (%d files)", stats.get("file_count", 0))
            return {"action": "none", "changed_files": 0, **stats}

        for f in changed_files:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            self._index_file(f, content)

        conn.commit()
        stats = self.get_stats()
        logger.info(
            "CodeStructureIndex: indexed %d files, total symbols=%d, call_edges=%d",
            len(changed_files), stats.get("symbol_count", 0), stats.get("call_edge_count", 0),
        )
        return {"action": "full" if force_full else "incremental", "changed_files": len(changed_files), **stats}

    def _index_file(self, file_path: Path, content: str):
        conn = self._get_conn()
        fkey = str(file_path)
        content_hash = self._hash_content(content)
        language = self._detect_language(file_path.suffix)
        line_count = content.count("\n") + 1

        with self._lock:
            conn.execute("DELETE FROM symbols WHERE file_path=?", (fkey,))
            conn.execute("DELETE FROM call_edges WHERE caller_file=?", (fkey,))
            conn.execute("DELETE FROM imports WHERE file_path=?", (fkey,))
            conn.execute("DELETE FROM inheritance WHERE file_path=?", (fkey,))
            conn.execute("DELETE FROM decorators WHERE file_path=?", (fkey,))

            conn.execute(
                "INSERT OR REPLACE INTO files (file_path, content_hash, language, line_count, last_indexed_at) "
                "VALUES (?, ?, ?, ?, datetime('now'))",
                (fkey, content_hash, language, line_count),
            )

            if file_path.suffix == ".py":
                self._index_python(conn, fkey, content)
            elif TREE_SITTER_AVAILABLE:
                ts_parsers = self._init_ts_parsers()
                parser = ts_parsers.get(file_path.suffix.lower())
                if parser:
                    self._index_tree_sitter(conn, fkey, content, parser)

    def _index_python(self, conn: sqlite3.Connection, fkey: str, content: str):
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        lines = content.split("\n")

        import_map: Dict[str, str] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                source_file = node.module.replace(".", "/") + ".py"
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    import_map[local_name] = source_file
                    conn.execute(
                        "INSERT OR IGNORE INTO imports (file_path, import_text, imported_symbol, source_file) VALUES (?, ?, ?, ?)",
                        (fkey, lines[node.lineno - 1].strip(), alias.name, source_file),
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    source_file = alias.name.replace(".", "/") + ".py"
                    import_map[local_name] = source_file
                    conn.execute(
                        "INSERT OR IGNORE INTO imports (file_path, import_text, imported_symbol, source_file) VALUES (?, ?, ?, ?)",
                        (fkey, lines[node.lineno - 1].strip(), alias.name, source_file),
                    )

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sig = lines[node.lineno - 1].strip()
                docstring = ast.get_docstring(node) or ""
                conn.execute(
                    "INSERT INTO symbols (file_path, name, kind, start_line, end_line, signature, docstring) "
                    "VALUES (?, ?, 'class', ?, ?, ?, ?)",
                    (fkey, node.name, node.lineno, node.end_lineno, sig, docstring),
                )
                for base in node.bases:
                    parent_name = ""
                    if isinstance(base, ast.Name):
                        parent_name = base.id
                    elif isinstance(base, ast.Attribute):
                        parent_name = base.attr
                    if parent_name:
                        parent_file = import_map.get(parent_name, "")
                        conn.execute(
                            "INSERT OR IGNORE INTO inheritance (file_path, class_name, parent_name, parent_file) VALUES (?, ?, ?, ?)",
                            (fkey, node.name, parent_name, parent_file),
                        )
                for dec in node.decorator_list:
                    dec_name = self._extract_decorator_name(dec)
                    dec_args = self._extract_decorator_args(dec, lines)
                    if dec_name:
                        conn.execute(
                            "INSERT OR IGNORE INTO decorators (file_path, symbol_name, decorator_name, decorator_args) VALUES (?, ?, ?, ?)",
                            (fkey, node.name, dec_name, dec_args),
                        )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_sig = lines[item.lineno - 1].strip()
                        method_doc = ast.get_docstring(item) or ""
                        conn.execute(
                            "INSERT INTO symbols (file_path, name, kind, start_line, end_line, signature, docstring) "
                            "VALUES (?, ?, 'method', ?, ?, ?, ?)",
                            (fkey, item.name, item.lineno, item.end_lineno, method_sig, method_doc),
                        )
                        for dec in item.decorator_list:
                            dec_name = self._extract_decorator_name(dec)
                            dec_args = self._extract_decorator_args(dec, lines)
                            if dec_name:
                                conn.execute(
                                    "INSERT OR IGNORE INTO decorators (file_path, symbol_name, decorator_name, decorator_args) VALUES (?, ?, ?, ?)",
                                    (fkey, f"{node.name}.{item.name}", dec_name, dec_args),
                                )
                        callees = self._extract_python_callees(item)
                        for callee_name in callees:
                            callee_file = self._resolve_callee_file(callee_name, import_map, fkey)
                            conn.execute(
                                "INSERT OR IGNORE INTO call_edges (caller_file, caller_name, callee_file, callee_name) "
                                "VALUES (?, ?, ?, ?)",
                                (fkey, f"{node.name}.{item.name}", callee_file, callee_name),
                            )

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = lines[node.lineno - 1].strip()
                docstring = ast.get_docstring(node) or ""
                conn.execute(
                    "INSERT INTO symbols (file_path, name, kind, start_line, end_line, signature, docstring) "
                    "VALUES (?, ?, 'function', ?, ?, ?, ?)",
                    (fkey, node.name, node.lineno, node.end_lineno, sig, docstring),
                )
                for dec in node.decorator_list:
                    dec_name = self._extract_decorator_name(dec)
                    dec_args = self._extract_decorator_args(dec, lines)
                    if dec_name:
                        conn.execute(
                            "INSERT OR IGNORE INTO decorators (file_path, symbol_name, decorator_name, decorator_args) VALUES (?, ?, ?, ?)",
                            (fkey, node.name, dec_name, dec_args),
                        )
                callees = self._extract_python_callees(node)
                for callee_name in callees:
                    callee_file = self._resolve_callee_file(callee_name, import_map, fkey)
                    conn.execute(
                        "INSERT OR IGNORE INTO call_edges (caller_file, caller_name, callee_file, callee_name) "
                        "VALUES (?, ?, ?, ?)",
                        (fkey, node.name, callee_file, callee_name),
                    )

    @staticmethod
    def _resolve_callee_file(callee_name: str, import_map: Dict[str, str], current_file: str) -> str:
        if callee_name in import_map:
            return import_map[callee_name]
        return current_file

    @staticmethod
    def _extract_decorator_name(dec_node: ast.AST) -> str:
        if isinstance(dec_node, ast.Name):
            return dec_node.id
        if isinstance(dec_node, ast.Attribute):
            return dec_node.attr
        if isinstance(dec_node, ast.Call):
            return CodeStructureIndex._extract_decorator_name(dec_node.func)
        return ""

    @staticmethod
    def _extract_decorator_args(dec_node: ast.AST, lines: List[str]) -> str:
        if isinstance(dec_node, ast.Call) and dec_node.args:
            try:
                args_text = lines[dec_node.lineno - 1]
                return args_text.strip()[:200]
            except (IndexError, AttributeError):
                pass
        return ""

    @staticmethod
    def _extract_python_callees(func_node: ast.AST) -> Set[str]:
        callees: Set[str] = set()
        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    callees.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    callees.add(child.func.attr)
        return callees

    def _index_tree_sitter(self, conn: sqlite3.Connection, fkey: str, content: str, parser):
        tree = parser.parse(bytes(content, "utf-8"))
        lines = content.split("\n")

        func_types = {
            "function_definition", "function_declaration",
            "function_item", "function_signature_item",
            "method_definition", "method_declaration",
            "method", "arrow_function",
            "generator_function_declaration", "constructor_definition",
        }
        class_types = {
            "class_definition", "class_declaration",
            "class_specifier", "class", "struct_specifier",
            "struct_item", "impl_item", "interface_declaration",
            "enum_declaration", "enum_item", "trait_item",
            "type_declaration", "type_spec",
            "module_declaration", "namespace_definition", "singleton_class",
        }
        import_types = {
            "import_statement", "import_from_statement",
            "import_declaration", "require_statement",
            "use_statement", "use_declaration",
            "include_directive", "preproc_include",
            "using_directive",
        }
        call_types = {"call_expression", "function_call"}
        name_types = ("identifier", "name", "property_identifier", "type_identifier", "field_identifier", "constant", "namespace_identifier")
        decorator_types = {"decorator", "attribute", "annotation"}
        superclass_types = {"superclass", "base_class", "argument_list", "type_identifier", "identifier"}

        import_map: Dict[str, str] = {}

        def _node_name(node):
            for child in node.children:
                if child.type in name_types:
                    text = child.text
                    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
            for child in node.children:
                if child.type == "function_declarator":
                    for sub in child.children:
                        if sub.type in ("identifier", "name", "field_identifier"):
                            text = sub.text
                            return text.decode("utf-8") if isinstance(text, bytes) else str(text)
            return ""

        def _node_text(node):
            text = node.text
            return text.decode("utf-8") if isinstance(text, bytes) else str(text)

        def _collect_imports(node):
            if node.type in import_types:
                import_text = _node_text(node).strip()
                if not (node.type == "call" and not import_text.startswith("require")):
                    sym = import_text.split()[-1].rstrip(";").split(".")[-1] if import_text else ""
                    source = ""
                    parts = import_text.replace("from ", "").replace("import ", "").split()
                    if parts:
                        source = parts[0].rstrip(";").replace(".", "/")
                        if not source.endswith((".py", ".js", ".ts", ".java", ".go", ".rs")):
                            source = source + "." + {"python": "py", "javascript": "js", "typescript": "ts", "java": "java", "go": "go", "rust": "rs", "ruby": "rb"}.get(self._detect_language(Path(fkey).suffix), "py")
                    conn.execute(
                        "INSERT OR IGNORE INTO imports (file_path, import_text, imported_symbol, source_file) VALUES (?, ?, ?, ?)",
                        (fkey, import_text, sym, source),
                    )
                    if sym:
                        import_map[sym] = source
            for child in node.children:
                _collect_imports(child)

        _collect_imports(tree.root_node)

        def _traverse(node, class_name: str = ""):
            if node.type in func_types:
                name = _node_name(node)
                if name:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    sig = lines[node.start_point[0]].strip() if node.start_point[0] < len(lines) else ""
                    kind = "method" if class_name else "function"
                    conn.execute(
                        "INSERT INTO symbols (file_path, name, kind, start_line, end_line, signature, docstring) "
                        "VALUES (?, ?, ?, ?, ?, ?, '')",
                        (fkey, name, kind, start_line, end_line, sig),
                    )
                    fqn = f"{class_name}.{name}" if class_name else name
                    for child in node.children:
                        if child.type in decorator_types:
                            dec_text = _node_text(child).strip().lstrip("@")
                            dec_name = dec_text.split("(")[0].split()[0] if dec_text else ""
                            if dec_name:
                                dec_args = dec_text[len(dec_name):].strip()[:200]
                                conn.execute(
                                    "INSERT OR IGNORE INTO decorators (file_path, symbol_name, decorator_name, decorator_args) VALUES (?, ?, ?, ?)",
                                    (fkey, fqn, dec_name, dec_args),
                                )
                    callees = self._extract_ts_callees(node, call_types, name_types)
                    for callee_name in callees:
                        callee_file = self._resolve_callee_file(callee_name, import_map, fkey)
                        conn.execute(
                            "INSERT OR IGNORE INTO call_edges (caller_file, caller_name, callee_file, callee_name) "
                            "VALUES (?, ?, ?, ?)",
                            (fkey, fqn, callee_file, callee_name),
                        )
                for child in node.children:
                    _traverse(child, class_name)
                return

            if node.type in class_types:
                name = _node_name(node)
                if name:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    sig = lines[node.start_point[0]].strip() if node.start_point[0] < len(lines) else ""
                    conn.execute(
                        "INSERT INTO symbols (file_path, name, kind, start_line, end_line, signature, docstring) "
                        "VALUES (?, ?, 'class', ?, ?, ?, '')",
                        (fkey, name, start_line, end_line, sig),
                    )
                    for child in node.children:
                        if child.type in decorator_types:
                            dec_text = _node_text(child).strip().lstrip("@")
                            dec_name = dec_text.split("(")[0].split()[0] if dec_text else ""
                            if dec_name:
                                conn.execute(
                                    "INSERT OR IGNORE INTO decorators (file_path, symbol_name, decorator_name, decorator_args) VALUES (?, ?, ?, ?)",
                                    (fkey, name, dec_name, ""),
                                )
                    for child in node.children:
                        if child.type in ("superclass", "base_class", "argument_list"):
                            for sub in child.children:
                                if sub.type in name_types:
                                    parent_name = _node_text(sub)
                                    if parent_name:
                                        parent_file = import_map.get(parent_name, "")
                                        conn.execute(
                                            "INSERT OR IGNORE INTO inheritance (file_path, class_name, parent_name, parent_file) VALUES (?, ?, ?, ?)",
                                            (fkey, name, parent_name, parent_file),
                                        )
                    for child in node.children:
                        _traverse(child, class_name=name)
                    return

            for child in node.children:
                _traverse(child, class_name)

        _traverse(tree.root_node)

    @staticmethod
    def _extract_ts_callees(func_node, call_types: set, name_types: tuple) -> Set[str]:
        callees: Set[str] = set()

        def _walk(n):
            if n.type in call_types:
                for child in n.children:
                    if child.type in name_types:
                        text = child.text
                        callees.add(text.decode("utf-8") if isinstance(text, bytes) else str(text))
                        break
            for child in n.children:
                _walk(child)

        _walk(func_node)
        return callees

    def get_stats(self) -> Dict[str, int]:
        conn = self._get_conn()
        files = conn.execute("SELECT COUNT(*) as c FROM files").fetchone()["c"]
        symbols = conn.execute("SELECT COUNT(*) as c FROM symbols").fetchone()["c"]
        edges = conn.execute("SELECT COUNT(*) as c FROM call_edges").fetchone()["c"]
        imports = conn.execute("SELECT COUNT(*) as c FROM imports").fetchone()["c"]
        inh = conn.execute("SELECT COUNT(*) as c FROM inheritance").fetchone()["c"]
        dec = conn.execute("SELECT COUNT(*) as c FROM decorators").fetchone()["c"]
        return {
            "file_count": files, "symbol_count": symbols,
            "call_edge_count": edges, "import_count": imports,
            "inheritance_count": inh, "decorator_count": dec,
        }

    def query_symbols_in_file(self, file_path: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT name, kind, start_line, end_line, signature FROM symbols WHERE file_path=? ORDER BY start_line",
            (file_path,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_symbol(self, name: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if kind:
            rows = conn.execute(
                "SELECT file_path, name, kind, start_line, end_line, signature FROM symbols WHERE name=? AND kind=?",
                (name, kind),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT file_path, name, kind, start_line, end_line, signature FROM symbols WHERE name=?",
                (name,),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_callers_of(self, callee_name: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT caller_file, caller_name FROM call_edges WHERE callee_name=?",
            (callee_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_callees_of(self, caller_name: str, caller_file: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if caller_file:
            rows = conn.execute(
                "SELECT callee_file, callee_name FROM call_edges WHERE caller_name=? AND caller_file=?",
                (caller_name, caller_file),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT callee_file, callee_name FROM call_edges WHERE caller_name=?",
                (caller_name,),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_imports_of_file(self, file_path: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT import_text, imported_symbol FROM imports WHERE file_path=?",
            (file_path,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_files_by_import(self, imported_symbol: str) -> List[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT file_path FROM imports WHERE imported_symbol=?",
            (imported_symbol,),
        ).fetchall()
        return [r["file_path"] for r in rows]

    def query_inheritance_of(self, class_name: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, class_name, parent_name, parent_file FROM inheritance WHERE class_name=?",
            (class_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_subclasses_of(self, parent_name: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, class_name, parent_name, parent_file FROM inheritance WHERE parent_name=?",
            (parent_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_decorators_of(self, symbol_name: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, symbol_name, decorator_name, decorator_args FROM decorators WHERE symbol_name=?",
            (symbol_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_by_decorator(self, decorator_name: str) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, symbol_name, decorator_name, decorator_args FROM decorators WHERE decorator_name=?",
            (decorator_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_enriched_symbol(self, name: str) -> Dict[str, Any]:
        """查询符号的完整信息：签名+docstring+调用链+继承+装饰器"""
        result: Dict[str, Any] = {"name": name, "symbols": [], "callers": [], "callees": [], "inheritance": [], "decorators": []}
        result["symbols"] = self.query_symbol(name)
        result["callers"] = self.query_callers_of(name)
        result["callees"] = self.query_callees_of(name)
        result["inheritance"] = self.query_inheritance_of(name)
        if not result["inheritance"]:
            result["inheritance"] = self.query_subclasses_of(name)
        result["decorators"] = self.query_decorators_of(name)
        return result

    def query_symbols_fuzzy(self, pattern: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, name, kind, start_line, end_line, signature FROM symbols WHERE name LIKE ? LIMIT ?",
            (f"%{pattern}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_affected_files(self, changed_symbol: str) -> List[str]:
        """给定变更符号，通过调用图反向传播找出所有受影响的文件"""
        from collections import deque
        conn = self._get_conn()
        visited: Set[str] = set()
        queue = deque([changed_symbol])
        affected_files: Set[str] = set()

        while queue:
            sym = queue.popleft()
            if sym in visited:
                continue
            visited.add(sym)
            rows = conn.execute(
                "SELECT caller_file, caller_name FROM call_edges WHERE callee_name=?",
                (sym,),
            ).fetchall()
            for r in rows:
                affected_files.add(r["caller_file"])
                queue.append(r["caller_name"])

        return list(affected_files)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
