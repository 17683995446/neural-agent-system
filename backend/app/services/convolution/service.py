"""
卷积层服务 - 代码局部分析
对应CNN的卷积操作，以固定视野范围扫描代码工程
LLM优先语义分析，降级到Tree-sitter/正则解析
"""
import os
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from app.core.llm_client import create_llm_client
from app.core.llm_utils import extract_json_from_llm_response
from app.core.io_utils import save_layer_output
from app.core.logging import logger as app_logger
from app.core.ast_cache import ASTCache
from app.core.cheap_llm_client import CheapLLMClient
from app.core.agent_scheduler import AgentScheduler
from app.core.code_index import CodeStructureIndex
from app.services.convolution.module_partitioner import ModulePartitioner, Module
from app.services.convolution.change_detector import ChangeDetector, ChangeSet

logger = app_logger

# 每Agent默认并发数
MAX_CONCURRENT_AGENTS = min(os.cpu_count() or 4, 10)


class ConvolutionConfig:
    """卷积核配置"""
    GRANULARITY_FILE = "file"
    GRANULARITY_FUNCTION = "function"
    GRANULARITY_MODULE = "module"

    def __init__(
        self,
        granularity: str = GRANULARITY_FILE,
        max_agents: int = 20
    ):
        self.granularity = granularity
        self.max_agents = max_agents


class CodeAnalyzer:
    """代码分析器 - 基于Tree-sitter的多语言AST解析"""

    SUPPORTED_LANGUAGES = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
    }

    _FUNCTION_NODES = {
        "function_definition",
        "function_declaration",
        "function_item",
        "function_signature_item",
        "method_definition",
        "method",
        "arrow_function",
        "generator_function_declaration",
        "method_declaration",
        "constructor_definition",
    }

    _CLASS_NODES = {
        "class_definition",
        "class_declaration",
        "class_specifier",
        "class",
        "struct_item",
        "struct_specifier",
        "impl_item",
        "interface_declaration",
        "enum_declaration",
        "enum_item",
        "trait_item",
        "type_declaration",
        "type_spec",
        "module_declaration",
        "namespace_definition",
        "singleton_class",
    }

    _IMPORT_NODES = {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "require_statement",
        "use_statement",
        "use_declaration",
        "include_directive",
        "preproc_include",
        "using_directive",
        "call",
    }

    def __init__(self):
        self.parsers: Dict[str, Parser] = {}
        self.languages: Dict[str, Language] = {}
        self._init_parsers()

    def _init_parsers(self):
        """初始化Tree-sitter解析器，加载各语言grammar"""
        if not TREE_SITTER_AVAILABLE:
            if logger:
                logger.warning("Tree-sitter not available, will use generic regex parser")
            return

        language_builders = {
            "python": lambda: Language(_ts_python.language()),
            "javascript": lambda: Language(_ts_javascript.language()),
            "typescript": lambda: Language(_ts_typescript.language_typescript()),
            "tsx": lambda: Language(_ts_typescript.language_tsx()),
            "java": lambda: Language(_ts_java.language()),
            "go": lambda: Language(_ts_go.language()),
            "rust": lambda: Language(_ts_rust.language()),
            "c": lambda: Language(_ts_c.language()),
            "cpp": lambda: Language(_ts_cpp.language()),
            "ruby": lambda: Language(_ts_ruby.language()),
        }

        for ext, lang_name in self.SUPPORTED_LANGUAGES.items():
            builder = language_builders.get(lang_name)
            if builder is None:
                continue
            try:
                lang = builder()
                parser = Parser(lang)
                self.parsers[ext] = parser
                self.languages[ext] = lang
                if logger:
                    logger.debug(f"Initialized tree-sitter parser for {lang_name} ({ext})")
            except Exception as e:
                if logger:
                    logger.warning(f"Failed to initialize parser for {lang_name} ({ext}): {e}")

        if logger:
            logger.info(f"Tree-sitter initialized: {len(self.parsers)} language parsers loaded")

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """解析代码文件，提取结构化信息"""
        path = Path(file_path)
        if not path.exists():
            return {"error": "File not found"}

        ext = path.suffix.lower()
        if ext in self.parsers:
            try:
                content = path.read_text(encoding="utf-8")
                return self._parse_with_tree_sitter(content, ext, file_path)
            except Exception as e:
                if logger:
                    logger.warning(f"Tree-sitter parse failed for {file_path}, falling back: {e}")
                return self._parse_generic(path)

        return self._parse_generic(path)

    def _parse_with_tree_sitter(self, content: str, ext: str, file_path: str) -> Dict[str, Any]:
        """使用Tree-sitter解析，提取函数/类/imports/变量等结构"""
        parser = self.parsers.get(ext)
        if not parser:
            return self._parse_generic(Path(file_path))

        tree = parser.parse(bytes(content, "utf-8"))
        root_node = tree.root_node

        functions = []
        classes = []
        imports = []
        variables = []

        def _node_name(node) -> str:
            name_types = (
                "identifier", "name", "property_identifier",
                "type_identifier", "field_identifier",
                "method_identifier", "simple_name",
                "call_expression", "constant",
                "namespace_identifier",
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
            if node.type in self._FUNCTION_NODES:
                name = _node_name(node)
                functions.append({
                    "name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                })
                return

            if node.type == "variable_declarator":
                has_arrow = any(c.type == "arrow_function" for c in node.children)
                if has_arrow:
                    name = _node_name(node)
                    functions.append({
                        "name": name,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                    })
                    return

            if node.type in self._CLASS_NODES:
                name = _node_name(node)
                classes.append({
                    "name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                })

                def _collect_methods(n):
                    for child in n.children:
                        if child.type in self._FUNCTION_NODES:
                            method_name = _node_name(child)
                            functions.append({
                                "name": method_name,
                                "start_line": child.start_point[0] + 1,
                                "end_line": child.end_point[0] + 1,
                            })
                        else:
                            _collect_methods(child)

                _collect_methods(node)
                return

            if node.type in self._IMPORT_NODES:
                text = node.text
                import_text = text.decode("utf-8") if isinstance(text, bytes) else str(text)
                if node.type == "call" and not import_text.lstrip().startswith("require"):
                    pass
                else:
                    imports.append(import_text)
                return

            for child in node.children:
                traverse(child)

        traverse(root_node)

        return {
            "file_path": file_path,
            "language": self.SUPPORTED_LANGUAGES.get(ext, "unknown"),
            "total_lines": content.count("\n") + 1,
            "functions": functions,
            "classes": classes,
            "imports": imports[:50],
            "variables": variables,
            "parsed_by": "tree-sitter",
        }

    def _parse_generic(self, path: Path) -> Dict[str, Any]:
        """通用正则解析（Tree-sitter不可用时的备选）— 支持多语言关键字"""
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")

            ext = path.suffix.lower()
            lang = self.SUPPORTED_LANGUAGES.get(ext, "unknown")

            func_patterns = {
                "python": ("def ", "(", ":"),
                "javascript": ("function ", "(", "{"),
                "typescript": ("function ", "(", "{"),
                "java": ("", "(", "{"),
                "go": ("func ", "(", "{"),
                "rust": ("fn ", "(", "{"),
                "c": ("", "(", "{"),
                "cpp": ("", "(", "{"),
                "ruby": ("def ", "", "end"),
            }

            functions = []
            classes = []

            kw = func_patterns.get(lang)
            if kw:
                prefix, _, _ = kw
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if lang == "python":
                        if stripped.startswith("def "):
                            func_name = stripped[4:].split("(")[0].strip()
                            functions.append({"name": func_name, "line": i})
                        elif stripped.startswith("class "):
                            class_name = stripped[6:].split("(")[0].split(":")[0].strip()
                            classes.append({"name": class_name, "line": i})
                    elif lang in ("javascript", "typescript"):
                        if stripped.startswith("function "):
                            func_name = stripped[9:].split("(")[0].strip()
                            functions.append({"name": func_name, "line": i})
                        elif stripped.startswith("class "):
                            class_name = stripped[6:].split("{")[0].split("extends")[0].strip()
                            classes.append({"name": class_name, "line": i})
                    elif lang == "java":
                        if "class " in stripped:
                            parts = stripped.split("class ")
                            if len(parts) > 1:
                                class_name = parts[1].split("{")[0].split("extends")[0].split("implements")[0].strip()
                                if class_name and class_name[0].isalpha():
                                    classes.append({"name": class_name, "line": i})
                        if "void " in stripped or "static " in stripped or "public " in stripped or "private " in stripped:
                            if "(" in stripped and ")" in stripped:
                                before_paren = stripped.split("(")[0].strip()
                                func_name = before_paren.split()[-1] if before_paren else ""
                                if func_name and func_name[0].isalpha():
                                    functions.append({"name": func_name, "line": i})
                    elif lang == "go":
                        if stripped.startswith("func "):
                            rest = stripped[5:].split("(")[0].strip()
                            func_name = rest.split(".")[-1] if rest else ""
                            functions.append({"name": func_name, "line": i})
                        elif stripped.startswith("type ") and "struct" in stripped:
                            class_name = stripped[5:].split("struct")[0].strip()
                            classes.append({"name": class_name, "line": i})
                    elif lang == "rust":
                        if stripped.startswith("fn "):
                            func_name = stripped[3:].split("(")[0].strip()
                            functions.append({"name": func_name, "line": i})
                        elif stripped.startswith("struct ") or stripped.startswith("enum ") or stripped.startswith("trait "):
                            kw_len = len(stripped.split()[0]) + 1
                            class_name = stripped[kw_len:].split("{")[0].split("<")[0].strip()
                            classes.append({"name": class_name, "line": i})
                    elif lang in ("c", "cpp"):
                        if stripped.startswith("class ") or stripped.startswith("struct "):
                            kw_len = len(stripped.split()[0]) + 1
                            class_name = stripped[kw_len:].split("{")[0].split(":")[0].strip()
                            classes.append({"name": class_name, "line": i})
                    elif lang == "ruby":
                        if stripped.startswith("def "):
                            func_name = stripped[4:].split("(")[0].strip()
                            functions.append({"name": func_name, "line": i})
                        elif stripped.startswith("class "):
                            class_name = stripped[6:].split("<")[0].strip()
                            classes.append({"name": class_name, "line": i})

            return {
                "file_path": str(path),
                "language": lang,
                "total_lines": len(lines),
                "functions": functions,
                "classes": classes,
                "imports": self._extract_imports(content, lang),
                "parsed_by": "generic",
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _extract_imports(content: str, lang: str = "python") -> List[str]:
        """多语言import提取"""
        imports = []
        for line in content.split("\n"):
            stripped = line.strip()
            if lang == "python":
                if stripped.startswith("import ") or stripped.startswith("from "):
                    imports.append(stripped)
            elif lang in ("javascript", "typescript"):
                if stripped.startswith("import ") or stripped.startswith("require("):
                    imports.append(stripped)
            elif lang == "java":
                if stripped.startswith("import "):
                    imports.append(stripped)
            elif lang == "go":
                if stripped.startswith("import "):
                    imports.append(stripped)
            elif lang == "rust":
                if stripped.startswith("use "):
                    imports.append(stripped)
            elif lang in ("c", "cpp"):
                if stripped.startswith("#include"):
                    imports.append(stripped)
            elif lang == "ruby":
                if stripped.startswith("require ") or stripped.startswith("require_relative "):
                    imports.append(stripped)
            else:
                if stripped.startswith("import ") or stripped.startswith("from "):
                    imports.append(stripped)
        return imports[:50]


class ConvolutionLayerService:
    """卷积层服务"""

    def __init__(self, config: Optional[ConvolutionConfig] = None):
        self.config = config or ConvolutionConfig()
        self.code_analyzer = CodeAnalyzer()
        self.llm_client = create_llm_client()
        self._ast_cache = ASTCache()
        self._change_detector: Optional[ChangeDetector] = None
        self._module_partitioner = ModulePartitioner()
        self._last_analysis: Dict[str, Dict] = {}
        self._agent_scheduler: Optional[AgentScheduler] = None
        self._cheap_llm_client: Optional[CheapLLMClient] = None
        self._code_index = CodeStructureIndex()
        self._last_analysis_path = Path(".cache/convolution/last_analysis.pkl")
        self._load_last_analysis()

    def analyze_file_with_llm(self, file_path: str, task_id: str) -> Optional[Dict[str, Any]]:
        """LLM补充分析：仅用于生成文件功能概述summary"""
        if not self.llm_client.is_available:
            return None
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            content = path.read_text(encoding="utf-8")
            if len(content) > 8000:
                content = "\n".join(content.split("\n")[:100]) + "\n# ... (truncated)"

            prompt = f"""简要概括以下代码文件的功能，一句话即可。

文件: {path.name}
代码:
```
{content}
```
只返回一句话的功能概述，不要JSON。"""
            response = self.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=256
            )
            text = self.llm_client.get_response_text(response)
            if text:
                return {"summary": text.strip()}
            return None
        except Exception as e:
            logger.warning(f"[LLM] Conv summary failed for {file_path}: {e}")
            return None

    def get_code_files(self, code_repo_path: str) -> List[str]:
        """获取代码工程中的代码文件"""
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
            ".go", ".rs", ".cpp", ".c", ".h", ".hpp",
            ".rb", ".php", ".cs", ".swift", ".kt"
        }

        code_files = []
        repo_path = Path(code_repo_path)

        if not repo_path.exists():
            logger.warning(f"Code repo path does not exist: {code_repo_path}")
            return []

        for ext in code_extensions:
            code_files.extend([
                str(f) for f in repo_path.rglob(f"*{ext}")
                if not self._is_excluded(f)
            ])

        # 限制Agent数量
        if len(code_files) > self.config.max_agents:
            logger.info(f"Too many files ({len(code_files)}), limiting to {self.config.max_agents}")
            code_files = code_files[:self.config.max_agents]

        return code_files

    def _is_excluded(self, path: Path) -> bool:
        """检查是否应该排除"""
        exclude_dirs = {
            "node_modules", ".git", "__pycache__", ".venv",
            "venv", "env", ".idea", ".vscode", "dist",
            "build", "target", "out", ".pytest_cache"
        }
        exclude_patterns = {"test_", "_test.", "tests.", ".min.js"}

        path_str = str(path)
        for ex_dir in exclude_dirs:
            if ex_dir in path_str:
                return True

        name = path.name
        for pattern in exclude_patterns:
            if pattern in name:
                return True

        return False

    def analyze_file(self, file_path: str, task_id: str) -> Dict[str, Any]:
        """分析单个代码文件 - Tree-sitter优先(AST确定性解析)，LLM仅补充summary"""
        logger.info(f"Analyzing file: {file_path} for task {task_id}")

        result = self._ast_cache.get_or_parse(
            Path(file_path),
            lambda p: self.code_analyzer.parse_file(str(p))
        )
        result["task_id"] = task_id
        result["analyzed_at"] = datetime.now().isoformat()

        llm_result = self.analyze_file_with_llm(file_path, task_id)
        if llm_result and "summary" in llm_result:
            result["summary"] = llm_result["summary"]

        return result

    def analyze_files(self, file_paths: List[str], task_id: str) -> List[Dict[str, Any]]:
        """并行分析多个代码文件 — 自动选择agent_pool或ThreadPool"""
        if not file_paths:
            return []

        if self._agent_scheduler is not None and self._cheap_llm_client is not None:
            return self._analyze_files_with_agent_pool(file_paths, task_id)

        results = []
        completed = 0
        total = len(file_paths)

        logger.info(f"[CONV] Starting parallel analysis of {total} files with {MAX_CONCURRENT_AGENTS} workers")

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_AGENTS) as executor:
            future_to_file = {
                executor.submit(self._analyze_file_with_dedicated_client, fp, task_id): fp
                for fp in file_paths
            }

            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    if completed % 10 == 0 or completed == total:
                        logger.info(f"[CONV] Progress: {completed}/{total} files analyzed")
                except Exception as e:
                    logger.error(f"Failed to analyze {file_path}: {e}")
                    results.append({
                        "file_path": file_path,
                        "error": str(e),
                        "task_id": task_id
                    })
                    completed += 1

        logger.info(f"[CONV] Completed analysis of {len(results)} files")
        return results

    def enable_agent_pool(self, max_workers: int = 0):
        """启用无限agent池模式 — 使用极便宜LLM"""
        self._cheap_llm_client = CheapLLMClient()
        self._agent_scheduler = AgentScheduler(max_workers=max_workers or None)
        logger.info(
            "Conv: agent pool enabled (workers=%d, cheap_llm=%s)",
            self._agent_scheduler.pool.max_workers,
            self._cheap_llm_client.model,
        )

    def _analyze_files_with_agent_pool(
        self, file_paths: List[str], task_id: str
    ) -> List[Dict[str, Any]]:
        """使用无限agent池分析 — Tree-sitter优先解析, CheapLLM仅补充summary"""
        total = len(file_paths)
        logger.info("[CONV] AgentPool mode: %d files, %d workers", total, self._agent_scheduler.pool.max_workers)

        def analyze_single(fp: str) -> Dict[str, Any]:
            try:
                path = Path(fp)
                if not path.exists():
                    return {"error": "File not found", "file_path": fp, "task_id": task_id}

                result = self._ast_cache.get_or_parse(
                    path, lambda p: self.code_analyzer.parse_file(str(p))
                )
                result["task_id"] = task_id
                result["analyzed_at"] = datetime.now().isoformat()

                try:
                    cheap_client = CheapLLMClient()
                    content = path.read_text(encoding="utf-8")
                    if len(content) > 4000:
                        lines = content.split("\n")
                        content = "\n".join(lines[:80]) + f"\n# ... ({len(lines) - 80} more lines)"
                    prompt = f"简要概括以下代码文件的功能，一句话即可。\n文件: {path.name}\n代码:\n```\n{content}\n```\n只返回一句话概述。"
                    response = cheap_client.complete(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=256,
                    )
                    text = cheap_client.get_response_text(response)
                    if text:
                        result["summary"] = text.strip()
                        result["analyzed_by"] = "tree-sitter+cheap_llm"
                    else:
                        result["analyzed_by"] = "tree-sitter"
                except Exception:
                    result["analyzed_by"] = "tree-sitter"

                return result
            except Exception as e:
                logger.warning(f"[CONV] AgentPool analyze failed for {fp}: {e}")
                return {"error": str(e), "file_path": fp, "task_id": task_id}

        results = self._agent_scheduler.dispatch_file_analysis(
            analyze_single, file_paths
        )

        logger.info("[CONV] AgentPool: %d/%d files analyzed", len(results), total)
        return results

    def _analyze_file_with_dedicated_client(self, file_path: str, task_id: str) -> Dict[str, Any]:
        """Tree-sitter优先解析结构 + LLM仅补充summary（线程安全）"""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"error": "File not found", "file_path": file_path, "task_id": task_id}

            result = self._ast_cache.get_or_parse(
                path, lambda p: self.code_analyzer.parse_file(str(p))
            )
            result["task_id"] = task_id
            result["analyzed_at"] = datetime.now().isoformat()

            try:
                llm_client = create_llm_client()
                content = path.read_text(encoding="utf-8")
                if len(content) > 8000:
                    lines = content.split("\n")
                    content = "\n".join(lines[:100]) + f"\n# ... ({len(lines) - 100} more lines)"
                prompt = f"简要概括以下代码文件的功能，一句话即可。\n文件: {path.name}\n代码:\n```\n{content}\n```\n只返回一句话概述。"
                response = llm_client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=256
                )
                text = llm_client.get_response_text(response)
                if text:
                    result["summary"] = text.strip()
                    result["analyzed_by"] = "tree-sitter+llm"
                else:
                    result["analyzed_by"] = "tree-sitter"
            except Exception:
                result["analyzed_by"] = "tree-sitter"

            return result
        except Exception as e:
            logger.warning(f"[CONV] analyze failed for {file_path}: {e}")
            return {"error": str(e), "file_path": file_path, "task_id": task_id}

    def create_convolution_output(
        self,
        analysis_results: List[Dict[str, Any]],
        task_id: str
    ) -> Dict[str, Any]:
        """创建卷积层输出"""
        output = {
            "task_id": task_id,
            "layer": "convolution",
            "total_files": len(analysis_results),
            "analyzed_files": [r for r in analysis_results if "error" not in r],
            "failed_files": [r for r in analysis_results if "error" in r],
            "summary": {
                "total_functions": sum(len(r.get("functions", [])) for r in analysis_results),
                "total_classes": sum(len(r.get("classes", [])) for r in analysis_results)
            },
            "created_at": datetime.now().isoformat()
        }

        return output

    def process_task(
        self,
        task_id: str,
        code_repo_path: str,
        *,
        force_full: bool = False,
        enable_module_partition: bool = True,
        enable_incremental: bool = True,
        user_requirement: str = "",
    ) -> Dict[str, Any]:
        logger.info("Convolution layer processing task %s", task_id)

        repo_path = Path(code_repo_path)
        target_files: Optional[List[str]] = None
        modules: Optional[List[Module]] = None

        if enable_module_partition:
            modules = self._module_partitioner.partition(repo_path)
            if user_requirement and modules:
                target_modules = self._module_partitioner.route_requirement(
                    user_requirement, modules
                )
                target_files = [str(f) for m in target_modules for f in m.files]
                logger.info(
                    "ModulePartitioner: routed to %d modules, %d files",
                    len(target_modules), len(target_files),
                )

        if enable_incremental and not force_full and self._change_detector is not None:
            changes = self._change_detector.detect_changes(repo_path)
            if changes.change_ratio < 0.1:
                output = self._incremental_analyze(task_id, changes)
                if output is not None:
                    save_layer_output(task_id, "convolution", output, "analysis_results.json")
                    return output

        if target_files is not None:
            code_files = target_files
        else:
            code_files = self.get_code_files(code_repo_path)
        logger.info("Found %d code files for task %s", len(code_files), task_id)

        index_result = self._code_index.build_index(repo_path)
        logger.info("Code index: %s", index_result)

        analysis_results = self.analyze_files(code_files, task_id)

        for r in analysis_results:
            fp = r.get("file_path", "")
            if fp:
                self._last_analysis[fp] = r
        self._save_last_analysis()

        output = self.create_convolution_output(analysis_results, task_id)
        if modules:
            output["modules"] = [
                {"name": m.name, "file_count": m.file_count, "dependencies": list(m.dependencies)}
                for m in modules
            ]

        save_layer_output(task_id, "convolution", output, "analysis_results.json")

        logger.info("Convolution layer completed for task %s", task_id)
        return output

    def enable_incremental(self, cache_dir: str = ".cache/changes"):
        self._change_detector = ChangeDetector(cache_dir=cache_dir)

    @property
    def code_index(self) -> CodeStructureIndex:
        return self._code_index

    def _load_last_analysis(self):
        try:
            from app.core.safe_pickle import safe_load_from_file
            data = safe_load_from_file(self._last_analysis_path)
            if isinstance(data, dict):
                self._last_analysis = data
                logger.info("Loaded last_analysis from disk: %d entries", len(data))
        except Exception as e:
            logger.debug("Failed to load last_analysis: %s", e)

    def _save_last_analysis(self):
        try:
            from app.core.safe_pickle import safe_dump_to_file
            self._last_analysis_path.parent.mkdir(parents=True, exist_ok=True)
            safe_dump_to_file(self._last_analysis, self._last_analysis_path)
        except Exception as e:
            logger.debug("Failed to save last_analysis: %s", e)

    def _incremental_analyze(self, task_id: str, changes: ChangeSet) -> Optional[Dict[str, Any]]:
        if not self._last_analysis:
            return None

        results = []
        for f in changes.unchanged_files:
            cached = self._last_analysis.get(str(f))
            if cached:
                results.append(cached)

        if changes.changed_files:
            new_results = self.analyze_files(
                [str(f) for f in changes.changed_files], task_id
            )
            results.extend(new_results)
            for r in new_results:
                fp = r.get("file_path", "")
                if fp:
                    self._last_analysis[fp] = r
            self._save_last_analysis()

        if not results:
            return None

        return self.create_convolution_output(results, task_id)


# Singleton instance
_convolution_service: Optional[ConvolutionLayerService] = None


def get_convolution_service() -> ConvolutionLayerService:
    """获取卷积层服务实例"""
    global _convolution_service
    if _convolution_service is None:
        _convolution_service = ConvolutionLayerService()
    return _convolution_service