"""
SmartContextWindow — 智能代码上下文
1. 定位目标符号的AST节点
2. 提取完整定义(永不截断!)
3. 提取直接依赖(调用的函数签名)
4. 提取类定义(如果目标是方法)
5. 提取imports
6. 剩余空间填充全局变量
支持多语言: Python(ast) + Tree-sitter(JS/TS/Java/Go/Rust/C/C++/Ruby)
"""
import ast
from pathlib import Path
from typing import Dict, List, Optional

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


class SmartContextWindow:
    _TS_PARSERS: Optional[Dict[str, Parser]] = None

    def __init__(self, max_chars: int = 12000):
        self.max_chars = max_chars

    @classmethod
    def _get_ts_parsers(cls) -> Dict[str, Parser]:
        if cls._TS_PARSERS is not None:
            return cls._TS_PARSERS
        if not TREE_SITTER_AVAILABLE:
            cls._TS_PARSERS = {}
            return cls._TS_PARSERS

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
        cls._TS_PARSERS = parsers
        return parsers

    def get_context(
        self,
        file_path: Path,
        target_symbol: str,
        code_content: Optional[str] = None,
    ) -> str:
        if code_content is None:
            try:
                code_content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ""

        if file_path.suffix == ".py":
            return self._get_context_python(code_content, target_symbol)

        ts_parsers = self._get_ts_parsers()
        parser = ts_parsers.get(file_path.suffix.lower())
        if parser:
            return self._get_context_tree_sitter(parser, code_content, target_symbol)

        return self._truncate_by_lines(code_content, max_lines=150)

    def _get_context_python(self, code_content: str, target_symbol: str) -> str:
        """Python文件：使用ast模块精确提取上下文"""
        try:
            tree = ast.parse(code_content)
        except SyntaxError:
            return self._truncate_by_lines(code_content, max_lines=150)

        lines = code_content.split("\n")
        sections: List[str] = []
        total_chars = 0

        imports = self._extract_imports(tree, lines)
        if imports:
            sections.append(imports)
            total_chars += len(imports)

        target_def = self._extract_symbol_definition(tree, lines, target_symbol)
        if target_def:
            sections.append(target_def)
            total_chars += len(target_def)

        class_def = self._extract_enclosing_class(tree, lines, target_symbol)
        if class_def and class_def not in target_def:
            if total_chars + len(class_def) <= self.max_chars:
                sections.append(class_def)
                total_chars += len(class_def)

        if total_chars < self.max_chars:
            deps = self._extract_dependencies(tree, lines, target_symbol)
            if deps:
                remaining = self.max_chars - total_chars
                deps_truncated = deps[:remaining]
                if deps_truncated:
                    sections.append(deps_truncated)
                    total_chars += len(deps_truncated)

        if total_chars < self.max_chars:
            header = self._extract_file_header(tree, lines)
            if header:
                remaining = self.max_chars - total_chars
                if len(header) > remaining:
                    header = header[:remaining] + "\n# ... (truncated)"
                sections.append(header)

        result = "\n\n".join(s for s in sections if s.strip())
        return result

    def _get_context_tree_sitter(self, parser: Parser, code_content: str, target_symbol: str) -> str:
        """非Python文件：使用Tree-sitter智能提取上下文"""
        tree = parser.parse(bytes(code_content, "utf-8"))
        lines = code_content.split("\n")
        sections: List[str] = []
        total_chars = 0

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
            "using_directive", "call",
        }

        imports = []
        target_def = ""
        class_def = ""

        def _node_name(node):
            name_types = (
                "identifier", "name", "property_identifier",
                "type_identifier", "field_identifier",
                "constant", "namespace_identifier",
            )
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
                if child.type == "type_spec":
                    for sub in child.children:
                        if sub.type in ("type_identifier", "identifier", "name"):
                            text = sub.text
                            return text.decode("utf-8") if isinstance(text, bytes) else str(text)
            return ""

        def traverse(node):
            nonlocal target_def, class_def
            if node.type in import_types:
                text = node.text
                import_text = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                if node.type == "call" and not import_text.lstrip().startswith("require"):
                    pass
                else:
                    imports.append(import_text)
                return

            if node.type in func_types:
                name = _node_name(node)
                if name == target_symbol:
                    start = node.start_point[0]
                    end = node.end_point[0]
                    target_def = "\n".join(lines[start:end])
                return

            if node.type in class_types:
                name = _node_name(node)
                if name == target_symbol:
                    start = node.start_point[0]
                    end = node.end_point[0]
                    target_def = "\n".join(lines[start:end])

                def _find_method_in_class(n):
                    nonlocal target_def, class_def
                    for child in n.children:
                        if child.type in func_types:
                            mname = _node_name(child)
                            if mname == target_symbol and not target_def:
                                start = child.start_point[0]
                                end = child.end_point[0]
                                target_def = "\n".join(lines[start:end])
                                cstart = node.start_point[0]
                                cend = node.end_point[0]
                                class_def = "\n".join(lines[cstart:cend])
                        else:
                            _find_method_in_class(child)

                _find_method_in_class(node)
                return

            for child in node.children:
                traverse(child)

        traverse(tree.root_node)

        if imports:
            import_text = "\n".join(imports)
            sections.append(import_text)
            total_chars += len(import_text)

        if target_def:
            sections.append(target_def)
            total_chars += len(target_def)

        if class_def and class_def != target_def and total_chars + len(class_def) <= self.max_chars:
            sections.append(class_def)
            total_chars += len(class_def)

        if not target_def and not class_def:
            return self._truncate_by_lines(code_content, max_lines=150)

        return "\n\n".join(s for s in sections if s.strip())

    @staticmethod
    def _extract_imports(tree: ast.AST, lines: List[str]) -> str:
        import_lines = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_lines.append(lines[node.lineno - 1])
        return "\n".join(import_lines) if import_lines else ""

    @staticmethod
    def _extract_symbol_definition(
        tree: ast.AST, lines: List[str], target: str
    ) -> str:
        for node in ast.walk(tree):
            name = getattr(node, "name", None)
            if name == target and isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                start = node.lineno - 1
                end = node.end_lineno
                return "\n".join(lines[start:end])
        return ""

    @staticmethod
    def _extract_enclosing_class(
        tree: ast.AST, lines: List[str], target: str
    ) -> str:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(
                        item, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ) and item.name == target:
                        start = node.lineno - 1
                        end = node.end_lineno
                        return "\n".join(lines[start:end])
        return ""

    @staticmethod
    def _extract_dependencies(
        tree: ast.AST, lines: List[str], target: str
    ) -> str:
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name == target:
                called_names: set = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            called_names.add(child.func.id)
                        elif isinstance(child.func, ast.Attribute):
                            called_names.add(child.func.attr)

                sigs = []
                for other in ast.walk(tree):
                    if isinstance(
                        other, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        if other.name in called_names:
                            sig_line = lines[other.lineno - 1]
                            sigs.append(f"# dependency: {sig_line.strip()}")
                return "\n".join(sigs)
        return ""

    @staticmethod
    def _extract_file_header(tree: ast.AST, lines: List[str]) -> str:
        header_lines = []
        for i, line in enumerate(lines[:30]):
            if i == 0 and line.startswith("#"):
                header_lines.append(line)
            elif "=" in line and not line.startswith(" "):
                header_lines.append(f"# global: {line.strip()}")
        return "\n".join(header_lines)

    @staticmethod
    def _truncate_by_lines(content: str, max_lines: int = 150) -> str:
        lines = content.split("\n")
        if len(lines) <= max_lines:
            return content
        return "\n".join(lines[:max_lines]) + f"\n# ... ({len(lines) - max_lines} more lines)"
