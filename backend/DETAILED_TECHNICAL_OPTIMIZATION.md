# 100万行代码项目 — 详细技术优化方案

**目标**: 1M行(10000文件) → 50分钟内完成  
**当前**: 1M行 → 30小时(不可行)

---

## 一、卷积层优化 (当前瓶颈: max_agents=20, 覆盖率0.2%)

### 1.1 ModulePartitioner — 项目自动拆模块

**当前实现** (`convolution/service.py:252-276`):
```python
def get_code_files(self, code_repo_path):
    # rglob遍历17种扩展名 → 排除12个目录 → 截断到20个
    if len(code_files) > self.config.max_agents:  # max_agents=20
        code_files = code_files[:self.config.max_agents]  # 硬截断!
```

**优化实现**:

```python
# 新文件: app/services/convolution/module_partitioner.py

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
import re

@dataclass
class Module:
    name: str
    root: Path
    files: List[Path] = field(default_factory=list)
    dependencies: Set[str] = field(default_factory=set)  # 依赖的其他模块名
    entry_points: List[Path] = field(default_factory=list)
    file_count: int = 0
    total_lines: int = 0

class ModulePartitioner:
    """
    项目自动拆模块策略:
    1. 按目录结构拆分(src/api, src/core等)
    2. 按依赖图合并小模块
    3. 按文件数上限拆分大模块(每模块≤200文件)
    4. 需求路由: 仅分析需求相关的模块
    """
    
    MAX_FILES_PER_MODULE = 200
    MIN_FILES_PER_MODULE = 5
    
    def partition(self, project_root: Path) -> List[Module]:
        """三阶段拆分"""
        # 阶段1: 按目录结构初始拆分
        modules = self._partition_by_directory(project_root)
        
        # 阶段2: 分析模块间依赖(import关系)
        self._analyze_dependencies(modules)
        
        # 阶段3: 合并过小模块 / 拆分过大模块
        modules = self._merge_small_modules(modules)
        modules = self._split_large_modules(modules)
        
        return modules
    
    def _partition_by_directory(self, root: Path) -> List[Module]:
        """
        按一级子目录拆分:
        - src/api/ → Module("api")
        - src/core/ → Module("core")
        - tests/ → Module("tests")
        - 根目录文件 → Module("root")
        
        特殊处理:
        - 如果子目录<5个文件，归入父模块
        - 常见框架结构识别: Django(apps/), Spring(src/main/java/...)
        """
        modules = []
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
            ".go", ".rs", ".cpp", ".c", ".h", ".hpp",
            ".rb", ".php", ".cs", ".swift", ".kt"
        }
        
        # 扫描一级子目录
        subdirs = [d for d in root.iterdir() if d.is_dir() and not self._is_excluded_dir(d)]
        
        for subdir in subdirs:
            files = [f for f in subdir.rglob("*") 
                     if f.is_file() and f.suffix in code_extensions 
                     and not self._is_excluded(f)]
            if len(files) >= self.MIN_FILES_PER_MODULE:
                modules.append(Module(
                    name=subdir.name,
                    root=subdir,
                    files=files,
                    file_count=len(files)
                ))
        
        # 根目录文件
        root_files = [f for f in root.glob("*") 
                      if f.is_file() and f.suffix in code_extensions]
        if root_files:
            modules.append(Module(name="root", root=root, files=root_files, 
                                  file_count=len(root_files)))
        
        return modules
    
    def _analyze_dependencies(self, modules: List[Module]):
        """
        分析模块间import依赖:
        对每个模块的文件，扫描import语句
        如果import路径指向另一个模块的文件 → 建立依赖
        """
        module_file_map = {}
        for mod in modules:
            for f in mod.files:
                module_file_map[f.resolve()] = mod.name
        
        for mod in modules:
            for f in mod.files[:50]:  # 每模块最多扫描50个文件的import
                try:
                    content = f.read_text(encoding='utf-8', errors='replace')[:5000]
                    for line in content.split('\n'):
                        stripped = line.strip()
                        if stripped.startswith(('import ', 'from ')):
                            # 简化: 检查import路径是否包含其他模块名
                            for other_mod in modules:
                                if other_mod.name != mod.name and other_mod.name in stripped:
                                    mod.dependencies.add(other_mod.name)
                except Exception:
                    pass
    
    def _merge_small_modules(self, modules: List[Module]) -> List[Module]:
        """合并<5个文件的模块到其依赖最多的相邻模块"""
        merged = []
        small = [m for m in modules if m.file_count < self.MIN_FILES_PER_MODULE]
        large = [m for m in modules if m.file_count >= self.MIN_FILES_PER_MODULE]
        
        for s in small:
            # 找到依赖最多的目标模块
            target = None
            for dep_name in s.dependencies:
                target = next((m for m in large if m.name == dep_name), None)
                if target:
                    break
            if target:
                target.files.extend(s.files)
                target.file_count += s.file_count
            else:
                large.append(s)  # 无依赖则保留
        
        return large
    
    def _split_large_modules(self, modules: List[Module]) -> List[Module]:
        """拆分>200个文件的模块为子模块"""
        result = []
        for mod in modules:
            if mod.file_count <= self.MAX_FILES_PER_MODULE:
                result.append(mod)
                continue
            
            # 按二级子目录拆分
            subdirs = set(f.parent.relative_to(mod.root).parts[0] 
                         for f in mod.files if len(f.parent.relative_to(mod.root).parts) > 0)
            
            for subdir_name in subdirs:
                sub_files = [f for f in mod.files 
                            if len(f.parent.relative_to(mod.root).parts) > 0 
                            and f.parent.relative_to(mod.root).parts[0] == subdir_name]
                if sub_files:
                    result.append(Module(
                        name=f"{mod.name}/{subdir_name}",
                        root=mod.root / subdir_name,
                        files=sub_files,
                        file_count=len(sub_files)
                    ))
            
            # 无二级目录的文件归入原模块
            remaining = [f for f in mod.files 
                        if len(f.parent.relative_to(mod.root).parts) == 0]
            if remaining:
                result.append(Module(name=mod.name, root=mod.root, files=remaining,
                                    file_count=len(remaining)))
        
        return result
    
    def route_requirement(self, requirement: str, modules: List[Module], 
                          top_k: int = 5) -> List[Module]:
        """
        需求路由: 根据需求关键词匹配最相关的模块
        
        策略:
        1. 提取需求中的关键词
        2. 对每个模块，计算关键词与模块名/文件名的匹配分数
        3. 对匹配模块的依赖模块也加入(传递依赖)
        4. 返回top_k个最相关模块
        """
        keywords = set(re.findall(r'[a-zA-Z_]{3,}', requirement.lower()))
        
        scored = []
        for mod in modules:
            score = 0.0
            # 模块名匹配
            for kw in keywords:
                if kw in mod.name.lower():
                    score += 1.0
            # 文件名匹配(采样前20个)
            for f in mod.files[:20]:
                for kw in keywords:
                    if kw in f.stem.lower():
                        score += 0.5
            scored.append((score, mod))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # 取top_k + 传递依赖
        selected = set()
        for score, mod in scored:
            if len(selected) >= top_k:
                break
            if score > 0:
                selected.add(mod.name)
                # 加入直接依赖
                for dep in mod.dependencies:
                    selected.add(dep)
        
        return [m for m in modules if m.name in selected]
```

**效果**: 1M行 → ~50-100模块 → 需求路由选3-5个 → 分析300-1000文件(覆盖率3-10%)

---

### 1.2 ChangeDetector — 增量变更检测

**当前实现**: 每次迭代全量重算(5×耗时)

```python
# 新文件: app/services/convolution/change_detector.py

import hashlib
import json
import pickle
import ast
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any

@dataclass
class ChangeSet:
    """变更集"""
    changed_files: List[Path] = field(default_factory=list)
    changed_symbols: List[str] = field(default_factory=list)    # "file:func_name"
    affected_symbols: List[str] = field(default_factory=list)   # 调用链影响
    unchanged_files: List[Path] = field(default_factory=list)
    total_files: int = 0
    change_ratio: float = 0.0    # 变更比例

class ChangeDetector:
    """
    增量变更检测:
    1. 文件级: hash比较 → 找出新增/修改/删除
    2. 符号级: AST diff → 找出修改的函数/类
    3. 影响级: 调用链分析 → 标记受影响的函数
    """
    
    def __init__(self, cache_dir: str = ".cache/changes"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._file_hashes: Dict[str, str] = {}
        self._symbol_index: Dict[str, Set[str]] = {}  # file → {symbol_names}
        self._call_graph: Dict[str, Set[str]] = {}    # symbol → {called_symbols}
        self._load_cache()
    
    def _hash_file(self, path: Path) -> str:
        content = path.read_bytes()
        return hashlib.md5(content).hexdigest()
    
    def detect_changes(self, project_root: Path, 
                       code_extensions: set = {".py", ".js", ".ts"}) -> ChangeSet:
        """检测变更"""
        all_files = []
        for ext in code_extensions:
            all_files.extend(f for f in project_root.rglob(f"*{ext}") if f.is_file())
        
        changed = []
        unchanged = []
        
        for f in all_files:
            key = str(f.relative_to(project_root))
            current_hash = self._hash_file(f)
            previous_hash = self._file_hashes.get(key)
            
            if previous_hash is None or current_hash != previous_hash:
                changed.append(f)
                self._file_hashes[key] = current_hash
            else:
                unchanged.append(f)
        
        # 分析变更符号和影响
        changed_symbols = self._analyze_changed_symbols(changed)
        affected_symbols = self._propagate_effects(changed_symbols)
        
        change_set = ChangeSet(
            changed_files=changed,
            changed_symbols=changed_symbols,
            affected_symbols=affected_symbols,
            unchanged_files=unchanged,
            total_files=len(all_files),
            change_ratio=len(changed) / max(len(all_files), 1)
        )
        
        self._save_cache()
        return change_set
    
    def _analyze_changed_symbols(self, changed_files: List[Path]) -> List[str]:
        """AST diff: 找出修改的函数/类"""
        symbols = []
        for f in changed_files:
            if f.suffix != ".py":
                continue  # 仅Python支持AST diff
            try:
                tree = ast.parse(f.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(f"{f}:{node.name}")
                    elif isinstance(node, ast.ClassDef):
                        symbols.append(f"{f}:{node.name}")
            except Exception:
                pass
        return symbols
    
    def _propagate_effects(self, changed_symbols: List[str]) -> List[str]:
        """
        影响传播: 找出调用变更符号的其他符号
        简化实现: 基于调用图反向传播
        """
        affected = set()
        for sym in changed_symbols:
            # 找所有调用sym的符号
            for caller, callees in self._call_graph.items():
                if sym in callees:
                    affected.add(caller)
        return list(affected)
    
    def _load_cache(self):
        cache_file = self._cache_dir / "change_cache.pkl"
        if cache_file.exists():
            try:
                data = pickle.loads(cache_file.read_bytes())
                self._file_hashes = data.get("hashes", {})
                self._symbol_index = data.get("symbols", {})
                self._call_graph = data.get("call_graph", {})
            except Exception:
                pass
    
    def _save_cache(self):
        cache_file = self._cache_dir / "change_cache.pkl"
        data = {
            "hashes": self._file_hashes,
            "symbols": self._symbol_index,
            "call_graph": self._call_graph
        }
        cache_file.write_bytes(pickle.dumps(data))
```

**在卷积层中集成**:

```python
# convolution/service.py 修改

class ConvolutionLayerService:
    def __init__(self):
        self._change_detector = ChangeDetector()
        self._last_analysis: Dict[str, Dict] = {}  # file_path → analysis_result
    
    def process_task(self, task_id, code_repo_path, *, force_full=False):
        if not force_full:
            changes = self._change_detector.detect_changes(Path(code_repo_path))
            
            if changes.change_ratio < 0.1:  # 变更<10%, 增量模式
                return self._incremental_analyze(task_id, changes)
        
        # 全量分析(首次或大量变更)
        return self._full_analyze(task_id, code_repo_path)
    
    def _incremental_analyze(self, task_id, changes):
        """增量分析: 复用未变更文件的结果, 仅重算变更文件"""
        results = []
        
        # 复用未变更文件的上次分析结果
        for f in changes.unchanged_files:
            cached = self._last_analysis.get(str(f))
            if cached:
                results.append(cached)
        
        # 仅分析变更文件
        new_results = self.analyze_files([str(f) for f in changes.changed_files], task_id)
        results.extend(new_results)
        
        # 更新缓存
        for r in new_results:
            self._last_analysis[r.get("file_path", "")] = r
        
        return self.create_convolution_output(results, task_id)
```

**效果**: 每次迭代仅重算5%文件 → 5次迭代耗时 = 1x + 4×0.05x = 1.2x (节省76%)

---

### 1.3 ASTCache — 解析缓存

**当前实现**: 每次Tree-sitter重新parse所有文件，无缓存

```python
# 新文件: app/core/ast_cache.py

import pickle
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
import threading

class ASTCache:
    """AST解析缓存 (内存+磁盘)"""
    
    def __init__(self, cache_dir: str = ".cache/ast", max_memory: int = 500):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: Dict[str, Any] = {}      # hash → ast_tree
        self._max_memory = max_memory            # 最多缓存500个AST
        self._lock = threading.Lock()
    
    def get_or_parse(self, file_path: Path, parser_func) -> Any:
        """获取AST: 先查内存→再查磁盘→最后解析"""
        file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
        
        # 内存缓存
        with self._lock:
            if file_hash in self._memory:
                return self._memory[file_hash]
        
        # 磁盘缓存
        cache_file = self._cache_dir / f"{file_hash}.pkl"
        if cache_file.exists():
            try:
                tree = pickle.loads(cache_file.read_bytes())
                with self._lock:
                    self._memory[file_hash] = tree
                return tree
            except Exception:
                pass
        
        # 解析
        tree = parser_func(file_path)
        
        # 存储
        with self._lock:
            if len(self._memory) >= self._max_memory:
                # LRU: 删除最早的
                oldest = next(iter(self._memory))
                del self._memory[oldest]
            self._memory[file_hash] = tree
        
        try:
            cache_file.write_bytes(pickle.dumps(tree))
        except Exception:
            pass
        
        return tree
    
    def invalidate(self, file_path: Path):
        """文件变更时使缓存失效"""
        # 简化: 全部清空(精确实现需按hash清理)
        with self._lock:
            self._memory.clear()
```

---

## 二、池化层优化 (当前瓶颈: max_output_items=20, 丢95%信息)

### 2.1 HierarchicalCompressor — 三级压缩

**当前实现** (`pooling/service.py:189-192`):
```python
# 只取前10个文件,每文件5个函数/3个类 → 极度信息丢失
items_summary = "\n".join(
    f"File {r.get('file_path', '?')}: functions={[f['name'] for f in r.get('functions', [])[:5]]}, ..."
    for r in analysis_results[:10]  # 只看10个!
)
```

**优化实现**:

```python
# 新文件: app/services/pooling/hierarchical_compressor.py

from dataclasses import dataclass, field
from typing import List, Dict, Any
from pathlib import Path

@dataclass
class CompressedOutput:
    """三级压缩输出"""
    # L1: 模块级摘要 — 用于FC1理解项目全貌
    module_summaries: List[Dict[str, Any]] = field(default_factory=list)
    # L2: 文件级摘要 — 用于FC1/FD2定位修改目标
    file_summaries: List[Dict[str, Any]] = field(default_factory=list)
    # L3: 函数级详情 — 用于FC2生成具体修改
    function_details: List[Dict[str, Any]] = field(default_factory=list)
    # 统计
    total_modules: int = 0
    total_files_scanned: int = 0
    total_functions_scanned: int = 0

class HierarchicalCompressor:
    """
    三级压缩:
    L1 - 模块摘要(全部保留, 每模块~50字)  → 100模块 = 5000字 ≈ 2000 tokens
    L2 - 文件摘要(相关模块, 每文件签名列表) → 200文件 = ~15000字 ≈ 6000 tokens  
    L3 - 函数详情(最相关, 完整签名+docstr)  → 50函数 = ~10000字 ≈ 4000 tokens
    总计: ~12000 tokens, 在LLM上下文窗口内
    """
    
    def __init__(self, 
                 max_module_summaries: int = 100,
                 max_file_summaries: int = 200,
                 max_function_details: int = 50):
        self.max_module_summaries = max_module_summaries
        self.max_file_summaries = max_file_summaries
        self.max_function_details = max_function_details
    
    def compress(self, analysis_results: List[Dict], 
                 user_requirement: str = "",
                 modules: List = None) -> CompressedOutput:
        
        output = CompressedOutput()
        output.total_files_scanned = len(analysis_results)
        
        # L1: 模块级摘要
        if modules:
            for mod in modules[:self.max_module_summaries]:
                output.module_summaries.append({
                    "name": mod.name,
                    "file_count": mod.file_count,
                    "dependencies": list(mod.dependencies)[:5],
                    "summary": self._summarize_module(mod, analysis_results)
                })
        else:
            # 无模块信息时,按目录分组
            dir_groups = self._group_by_directory(analysis_results)
            for dir_name, files in list(dir_groups.items())[:self.max_module_summaries]:
                output.module_summaries.append({
                    "name": dir_name,
                    "file_count": len(files),
                    "summary": f"{len(files)} files"
                })
        output.total_modules = len(output.module_summaries)
        
        # L2: 文件级摘要 (按相关性排序)
        scored_files = self._score_and_sort_files(analysis_results, user_requirement)
        for item in scored_files[:self.max_file_summaries]:
            output.file_summaries.append({
                "file_path": item.get("file_path", ""),
                "functions": [f.get("name", "") for f in item.get("functions", [])],
                "classes": [c.get("name", "") for c in item.get("classes", [])],
                "summary": item.get("summary", ""),
                "relevance": item.get("_relevance", 0)
            })
        
        # L3: 函数级详情 (最相关的函数完整信息)
        top_functions = self._extract_top_functions(
            scored_files[:self.max_file_summaries], 
            limit=self.max_function_details
        )
        for func in top_functions:
            output.function_details.append(func)
        
        output.total_functions_scanned = sum(
            len(r.get("functions", [])) for r in analysis_results
        )
        
        return output
    
    def _summarize_module(self, module, analysis_results) -> str:
        """生成模块摘要(50字以内)"""
        # 找属于该模块的文件
        mod_files = [r for r in analysis_results 
                     if any(str(f) in r.get("file_path", "") for f in module.files[:20])]
        total_funcs = sum(len(r.get("functions", [])) for r in mod_files)
        total_classes = sum(len(r.get("classes", [])) for r in mod_files)
        return f"{len(mod_files)} files, {total_funcs} functions, {total_classes} classes"
    
    def _group_by_directory(self, results: List[Dict]) -> Dict[str, List]:
        """按目录分组"""
        groups: Dict[str, List] = {}
        for r in results:
            fp = r.get("file_path", "")
            parts = Path(fp).parts
            dir_name = "/".join(parts[:2]) if len(parts) > 1 else "root"
            groups.setdefault(dir_name, []).append(r)
        return groups
    
    def _score_and_sort_files(self, results: List[Dict], requirement: str) -> List[Dict]:
        """按与需求的相关性排序"""
        keywords = set(requirement.lower().split()) if requirement else set()
        
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
    
    def _extract_top_functions(self, files: List[Dict], limit: int) -> List[Dict]:
        """提取最相关函数的完整签名"""
        functions = []
        for f in files:
            for func in f.get("functions", []):
                functions.append({
                    "name": func.get("name", ""),
                    "file_path": f.get("file_path", ""),
                    "line": func.get("line") or func.get("start_line"),
                    "class": func.get("class_name", ""),
                    "relevance": f.get("_relevance", 0)
                })
        
        functions.sort(key=lambda x: x["relevance"], reverse=True)
        return functions[:limit]
```

---

## 三、LLM调用优化 (当前瓶颈: 无限频, 429超时, max_tokens=4096)

### 3.1 LLMRateLimiter — 令牌桶限频

**当前实现** (`llm_client.py`): 无限频, ThreadPoolExecutor直接并发

```python
# 新文件: app/core/llm_rate_limiter.py

import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class LLMRateLimiter:
    """
    令牌桶限频器:
    - max_qps: 每秒最大请求数(控制429)
    - max_concurrent: 最大并发数(控制负载)
    - 支持多优先级: critical(方案规划) > normal(代码修改) > low(测试生成)
    """
    
    _instance: Optional['LLMRateLimiter'] = None
    _lock = threading.Lock()
    
    def __init__(self, max_qps: float = 3.0, max_concurrent: int = 5):
        self._max_qps = max_qps
        self._max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)
        self._tokens = max_qps
        self._last_refill = time.monotonic()
        self._total_requests = 0
        self._total_waited = 0.0
    
    @classmethod
    def get_instance(cls) -> 'LLMRateLimiter':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_qps=3.0, max_concurrent=5)
        return cls._instance
    
    @classmethod
    def configure(cls, max_qps: float, max_concurrent: int):
        with cls._lock:
            cls._instance = cls(max_qps=max_qps, max_concurrent=max_concurrent)
    
    def acquire(self, timeout: float = 300.0) -> bool:
        """获取调用许可(阻塞等待), 返回是否成功"""
        deadline = time.monotonic() + timeout
        
        # 限制并发
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            logger.warning("LLM rate limiter: concurrent limit reached")
            return False
        
        try:
            # 令牌桶等待
            while True:
                with self._lock:
                    now = time.monotonic()
                    elapsed = now - self._last_refill
                    self._tokens = min(self._max_qps, self._tokens + elapsed * self._max_qps)
                    self._last_refill = now
                    
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        self._total_requests += 1
                        return True
                    
                    wait = (1.0 - self._tokens) / self._max_qps
                
                if time.monotonic() + wait > deadline:
                    self._semaphore.release()
                    logger.warning("LLM rate limiter: timeout waiting for token")
                    return False
                
                time.sleep(wait)
                self._total_waited += wait
        except Exception:
            self._semaphore.release()
            return False
    
    def release(self):
        self._semaphore.release()
    
    def get_stats(self) -> Dict:
        return {
            "total_requests": self._total_requests,
            "total_waited_seconds": self._total_waited,
            "max_qps": self._max_qps,
            "max_concurrent": self._max_concurrent
        }
```

**在LLMClient中集成**:

```python
# llm_client.py 修改

def _make_request(self, messages, **kwargs):
    limiter = LLMRateLimiter.get_instance()
    if not limiter.acquire(timeout=300):
        raise requests.exceptions.RequestException("LLM rate limit timeout")
    try:
        url = f"{self.api_base}/v1/chat/completions"
        headers = {...}
        payload = {...}
        return requests.post(url, headers=headers, json=payload, timeout=(10, self.timeout))
    finally:
        limiter.release()
```

---

### 3.2 CircuitBreaker — 熔断器

```python
# 新文件: app/core/circuit_breaker.py

import time
import threading
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"        # 正常通行
    OPEN = "open"            # 熔断(拒绝所有请求)
    HALF_OPEN = "half_open"  # 半开(允许1个试探请求)

class CircuitBreaker:
    """
    熔断器:
    - 连续N次失败 → 熔断(OPEN), 直接返回fallback
    - 等待recovery_timeout → 半开(HALF_OPEN), 允许1个请求试探
    - 试探成功 → 恢复(CLOSED)
    - 试探失败 → 继续熔断(OPEN)
    """
    
    def __init__(self, name: str = "default",
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0):
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()
    
    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time > self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
            return self._state
    
    def call(self, func, *args, fallback=None, **kwargs):
        """通过熔断器调用函数"""
        state = self.state
        
        if state == CircuitState.OPEN:
            logger.warning(f"Circuit [{self._name}] is OPEN, using fallback")
            return fallback() if callable(fallback) else fallback
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if state == CircuitState.HALF_OPEN:
                logger.error(f"Circuit [{self._name}] HALF_OPEN probe failed: {e}")
            raise
    
    def _on_success(self):
        with self._lock:
            self._failure_count = 0
            self._success_count += 1
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info(f"Circuit [{self._name}] recovered to CLOSED")
    
    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(f"Circuit [{self._name}] blown to OPEN after {self._failure_count} failures")
```

**在LLMClient中集成**:

```python
# llm_client.py 修改

class LLMClient:
    def __init__(self, ...):
        ...
        self._circuit = CircuitBreaker("llm", failure_threshold=5, recovery_timeout=60)
    
    def complete(self, messages, ...):
        if not self.is_available:
            return self._make_fallback_response(fallback_text)
        
        return self._circuit.call(
            self._complete_internal,
            messages, model, fallback_text, **kwargs,
            fallback=lambda: self._make_fallback_response(fallback_text)
        )
    
    def _complete_internal(self, messages, model, fallback_text, **kwargs):
        """实际的重试逻辑(与当前相同)"""
        ...
```

---

### 3.3 LLMResponseCache — 响应缓存

```python
# 新文件: app/core/llm_cache.py

import hashlib
import json
import time
import threading
from typing import Dict, Any, Optional, Tuple, List

class LLMResponseCache:
    """
    LLM响应缓存:
    - 基于prompt内容的SHA256 hash
    - 内存缓存, TTL过期
    - LRU淘汰
    - 统计命中率
    """
    
    def __init__(self, ttl_seconds: float = 3600, max_size: int = 500):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
    
    def get(self, messages: List[Dict], **kwargs) -> Optional[Any]:
        key = self._make_key(messages, kwargs)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                result, timestamp = entry
                if time.monotonic() - timestamp < self._ttl:
                    self._hits += 1
                    return result
                else:
                    del self._cache[key]
            self._misses += 1
            return None
    
    def put(self, messages: List[Dict], result: Any, **kwargs):
        key = self._make_key(messages, kwargs)
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (result, time.monotonic())
    
    def _make_key(self, messages: List[Dict], kwargs: Dict) -> str:
        content = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        kw_str = json.dumps(kwargs, sort_keys=True, default=str)
        return hashlib.sha256((content + kw_str).encode()).hexdigest()[:32]
    
    def get_stats(self) -> Dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
            "cache_size": len(self._cache)
        }
```

---

## 四、FC1优化 (当前瓶颈: prompt只含15函数+10类, 看不到项目全貌)

### 4.1 ModularSolutionPlanner — 分层规划

**当前实现** (`service_fc1.py:59-63`):
```python
# prompt只含15个函数名+10个类名 → 1M行项目10万+函数完全看不到
func_info = "\n".join(f"  - {f['name']} (file: {f['file']})" for f in top_functions[:15])
class_info = "\n".join(f"  - {c['name']} (file: {c['file']})" for c in top_classes[:10])
```

**优化实现**:

```python
# 在 service_fc1.py 中新增

class ModularSolutionPlanner:
    """
    分模块三层规划:
    Step 1: 模块级(1次LLM) → 选择要修改的模块
    Step 2: 文件级(每模块1次LLM) → 选择要修改的文件
    Step 3: 函数级(每文件1次LLM) → 生成具体修改方案
    """
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def plan(self, user_requirement: str, 
             module_summaries: List[Dict],
             file_summaries: List[Dict],
             function_details: List[Dict]) -> Dict:
        
        # Step 1: 模块级规划
        target_modules = self._plan_modules(user_requirement, module_summaries)
        
        # Step 2: 文件级规划
        target_files = self._plan_files(user_requirement, target_modules, file_summaries)
        
        # Step 3: 函数级规划 (生成modification_list)
        solution = self._plan_functions(user_requirement, target_files, function_details)
        
        return solution
    
    def _plan_modules(self, requirement: str, modules: List[Dict]) -> List[str]:
        """Step 1: 选择需要修改的模块"""
        if not self.llm_client.is_available:
            # Fallback: 选择所有模块
            return [m["name"] for m in modules]
        
        module_list = "\n".join(
            f"  - {m['name']}: {m.get('summary', '')} ({m.get('file_count', 0)} files, deps={m.get('dependencies', [])})"
            for m in modules
        )
        
        prompt = f"""你是项目架构师。根据用户需求，判断哪些模块需要修改。

用户需求: {requirement}

项目模块:
{module_list}

返回JSON: {{"target_modules": ["模块名1", "模块名2"], "reason": "选择理由"}}
只返回JSON。"""
        
        result = self.llm_client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            fallback={"target_modules": [m["name"] for m in modules[:5]]},
            agent_name="fc1_module_plan"
        )
        
        return result.get("target_modules", [m["name"] for m in modules[:5]])
    
    def _plan_files(self, requirement: str, target_modules: List[str],
                    file_summaries: List[Dict]) -> List[Dict]:
        """Step 2: 在目标模块中选择需要修改的文件"""
        relevant_files = [f for f in file_summaries 
                         if any(m in f.get("file_path", "") for m in target_modules)]
        
        if not relevant_files:
            relevant_files = file_summaries[:50]
        
        if not self.llm_client.is_available:
            return relevant_files[:30]
        
        file_list = "\n".join(
            f"  - {f['file_path']}: funcs={[fn for fn in f.get('functions', [])[:10]]}, classes={[cn for cn in f.get('classes', [])[:5]]}"
            for f in relevant_files[:100]  # 最多100个文件摘要
        )
        
        prompt = f"""你是代码分析师。根据用户需求，判断哪些文件需要修改。

用户需求: {requirement}

相关文件:
{file_list}

返回JSON: {{"target_files": ["文件路径1", ...], "modification_overview": "修改概述"}}
只返回JSON。"""
        
        result = self.llm_client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            fallback={"target_files": [f["file_path"] for f in relevant_files[:20]]},
            agent_name="fc1_file_plan"
        )
        
        target_paths = result.get("target_files", [])
        return [f for f in relevant_files if f["file_path"] in target_paths]
    
    def _plan_functions(self, requirement: str, target_files: List[Dict],
                        function_details: List[Dict]) -> Dict:
        """Step 3: 对每个目标文件生成具体修改方案"""
        # 使用function_details中已有的函数详情
        # 此处逻辑与当前_generate_solution_llm类似，但上下文更丰富
        
        func_info = "\n".join(
            f"  - {fd['name']} in {fd['file_path']} (line {fd.get('line', '?')})"
            for fd in function_details[:50]  # 最多50个函数详情
        )
        
        prompt = f"""你是代码修改专家。根据用户需求和代码结构，生成修改方案。

用户需求: {requirement}

相关函数:
{func_info}

目标文件:
{chr(10).join(f"  - {f['file_path']}" for f in target_files[:30])}

返回JSON:
{{
  "overview": "方案概述",
  "modification_list": [
    {{"type": "function", "target": "函数名", "file": "文件路径", "action": "修改动作", "priority": "high/medium/low"}}
  ],
  "execution_order": ["target1", "target2"],
  "risk_points": [{{"type": "风险类型", "severity": "high/medium/low"}}]
}}
只返回JSON。"""
        
        result = self.llm_client.complete_json(
            messages=[{"role": "user", "content": prompt}],
            fallback=self._generate_rule_fallback(requirement, target_files),
            agent_name="fc1_func_plan",
            max_tokens=4096
        )
        
        if "modification_list" not in result:
            return self._generate_rule_fallback(requirement, target_files)
        
        return result
```

**LLM调用量**: Step1(1次) + Step2(1次) + Step3(1次) = 3次 (vs 当前1次但无效)

---

## 五、FC2优化 (当前瓶颈: 同文件覆盖, 代码截断80行)

### 5.1 ModificationDependencyGraph — 修改依赖图

**当前实现**: 50项修改全并行, 同文件多次写互相覆盖

```python
# 新文件: app/services/fullconnect/modification_graph.py

from typing import List, Dict, Any, Set
from collections import defaultdict
from pathlib import Path

class ModificationDependencyGraph:
    """
    修改依赖图:
    1. 同一文件的修改 → 串行(按行号排序)
    2. 文件A import文件B的符号 → B先改
    3. 无依赖的修改 → 可并行
    
    输出: 分层执行计划 List[List[Mod]]
    - 外层: 串行批次
    - 内层: 同批次可并行
    """
    
    def build_execution_plan(self, modifications: List[Dict]) -> List[List[Dict]]:
        """构建并排序执行计划"""
        # 按文件分组
        file_groups: Dict[str, List[Dict]] = defaultdict(list)
        for mod in modifications:
            fp = mod.get("file", "")
            file_groups[fp].append(mod)
        
        # 同文件内按行号排序
        for fp, mods in file_groups.items():
            mods.sort(key=lambda m: m.get("line") or 0)
        
        # 构建文件级依赖图
        file_deps = self._build_file_dependencies(file_groups)
        
        # 拓扑排序
        sorted_files = self._topological_sort(list(file_groups.keys()), file_deps)
        
        # 生成分层执行计划
        # 同一文件内的修改串行, 不同文件(无依赖)可并行
        plan = []
        processed_files = set()
        
        # 找到所有无依赖的文件作为第一批
        remaining = set(sorted_files)
        while remaining:
            # 当前批次: 所有依赖已被处理的文件
            batch_files = []
            for fp in sorted(remaining):
                deps = file_deps.get(fp, set())
                if deps.issubset(processed_files):
                    batch_files.append(fp)
            
            if not batch_files:
                # 死锁: 所有剩余文件都有未处理依赖, 强行加入
                batch_files = list(remaining)[:1]
            
            # 每个文件内的修改串行, 但不同文件可并行
            parallel_mods = []
            for fp in batch_files:
                for mod in file_groups[fp]:
                    parallel_mods.append({**mod, "_sequential_group": fp})
            
            plan.append(parallel_mods)
            
            for fp in batch_files:
                remaining.discard(fp)
                processed_files.add(fp)
        
        return plan
    
    def _build_file_dependencies(self, file_groups: Dict[str, List[Dict]]) -> Dict[str, Set[str]]:
        """分析文件间依赖"""
        deps: Dict[str, Set[str]] = defaultdict(set)
        # 简化: 如果文件A的修改target出现在文件B的import中, A依赖B
        # 实际需更精确的import分析
        return deps
    
    def _topological_sort(self, files: List[str], deps: Dict[str, Set[str]]) -> List[str]:
        """拓扑排序"""
        visited = set()
        result = []
        
        def visit(f):
            if f in visited:
                return
            visited.add(f)
            for dep in deps.get(f, set()):
                visit(dep)
            result.append(f)
        
        for f in files:
            visit(f)
        
        return result
```

**在FC2中集成**:

```python
# service_fc2.py 修改

def apply_modifications(self, modifications, code_repo_path):
    graph = ModificationDependencyGraph()
    execution_plan = graph.build_execution_plan(modifications)
    
    all_results = []
    file_state = {}  # file_path → 最新内容(解决同文件串行修改)
    
    for batch_idx, batch in enumerate(execution_plan):
        # 按sequential_group分组
        groups = defaultdict(list)
        for mod in batch:
            groups[mod["_sequential_group"]].append(mod)
        
        # 同文件串行, 不同文件并行
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_MODIFICATIONS) as executor:
            futures = {}
            for group_key, group_mods in groups.items():
                # 同文件的修改串行执行
                future = executor.submit(
                    self._apply_sequential_modifications,
                    group_mods, code_repo_path, file_state
                )
                futures[future] = group_key
            
            for future in as_completed(futures):
                results = future.result()
                all_results.extend(results)
                # 更新file_state
                for r in results:
                    if r.get("status") == "success":
                        fp = r.get("file_path", "")
                        if "modified_code" in r:
                            file_state[fp] = r["modified_code"]
    
    return all_results

def _apply_sequential_modifications(self, mods, code_repo_path, file_state):
    """同文件串行修改: 后续修改基于前次修改结果"""
    results = []
    for mod in mods:
        fp = mod.get("file", "")
        # 如果file_state有该文件最新内容, 用它而非原始文件
        code_context = file_state.get(fp)
        if code_context is None:
            full_path = Path(code_repo_path) / fp
            if full_path.exists():
                code_context = full_path.read_text(encoding="utf-8")
        
        result = self._apply_single_modification_with_context(mod, code_repo_path, code_context)
        results.append(result)
        
        # 更新file_state
        if result.get("status") == "success" and "modified_code" in result:
            file_state[fp] = result["modified_code"]
    
    return results
```

---

### 5.2 SmartContextWindow — 智能代码上下文

**当前实现**: 截断到80行, 大函数完全无法理解

```python
# 新文件: app/services/fullconnect/smart_context.py

import ast
from pathlib import Path
from typing import Optional, List, Tuple

class SmartContextWindow:
    """
    智能代码上下文:
    1. 定位目标符号的AST节点
    2. 提取完整定义(永不截断!)
    3. 提取直接依赖(调用的函数签名)
    4. 提取类定义(如果目标是方法)
    5. 提取imports
    6. 剩余空间填充全局变量
    """
    
    def __init__(self, max_chars: int = 6000):
        self.max_chars = max_chars
    
    def get_context(self, file_path: Path, target_symbol: str, 
                    code_content: str = None) -> str:
        if code_content is None:
            code_content = file_path.read_text(encoding="utf-8", errors='replace')
        
        # 非Python文件: 退回到行截断(但限制更大)
        if file_path.suffix != ".py":
            return self._truncate_by_lines(code_content, max_lines=150)
        
        try:
            tree = ast.parse(code_content)
        except SyntaxError:
            return self._truncate_by_lines(code_content, max_lines=150)
        
        lines = code_content.split('\n')
        sections = []
        total_chars = 0
        
        # 优先级1: imports (必须包含)
        imports = self._extract_imports(tree, lines)
        sections.append(imports)
        total_chars += len(imports)
        
        # 优先级2: 目标符号完整定义 (永不截断)
        target_def = self._extract_symbol_definition(tree, lines, target_symbol)
        if target_def:
            sections.append(target_def)
            total_chars += len(target_def)
        
        # 优先级3: 包含目标的类定义
        class_def = self._extract_enclosing_class(tree, lines, target_symbol)
        if class_def and class_def not in target_def:
            if total_chars + len(class_def) <= self.max_chars:
                sections.append(class_def)
                total_chars += len(class_def)
        
        # 优先级4: 目标符号调用的函数签名
        if total_chars < self.max_chars:
            deps = self._extract_dependencies(tree, lines, target_symbol)
            remaining = self.max_chars - total_chars
            deps = deps[:remaining]
            if deps:
                sections.append(deps)
                total_chars += len(deps)
        
        # 优先级5: 文件头注释/全局变量
        if total_chars < self.max_chars:
            header = self._extract_file_header(tree, lines)
            remaining = self.max_chars - total_chars
            if len(header) > remaining:
                header = header[:remaining] + "\n# ... (truncated)"
            sections.append(header)
        
        result = "\n\n".join(s for s in sections if s.strip())
        return result
    
    def _extract_imports(self, tree, lines) -> str:
        import_lines = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_lines.append(lines[node.lineno - 1])
        return "\n".join(import_lines) if import_lines else ""
    
    def _extract_symbol_definition(self, tree, lines, target: str) -> str:
        """提取目标函数/类的完整定义"""
        for node in ast.walk(tree):
            name = getattr(node, 'name', None)
            if name == target and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = node.lineno - 1
                end = node.end_lineno  # AST自动计算结束行
                return "\n".join(lines[start:end])
        return ""
    
    def _extract_enclosing_class(self, tree, lines, target: str) -> str:
        """如果target是方法, 提取包含它的类定义"""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == target:
                        start = node.lineno - 1
                        end = node.end_lineno
                        return "\n".join(lines[start:end])
        return ""
    
    def _extract_dependencies(self, tree, lines, target: str) -> str:
        """提取目标函数调用的其他函数的签名"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target:
                called_names = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            called_names.add(child.func.id)
                        elif isinstance(child.func, ast.Attribute):
                            called_names.add(child.func.attr)
                
                # 找到这些函数的签名
                sigs = []
                for other in ast.walk(tree):
                    if isinstance(other, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if other.name in called_names:
                            sig_line = lines[other.lineno - 1]
                            # 取函数签名(到冒号)
                            sigs.append(f"# dependency: {sig_line.strip()}")
                return "\n".join(sigs)
        return ""
    
    def _extract_file_header(self, tree, lines) -> str:
        """文件头部(docstring + 全局变量)"""
        header_lines = []
        for i, line in enumerate(lines[:30]):
            if i == 0 and line.startswith('#'):
                header_lines.append(line)
            elif '=' in line and not line.startswith(' '):
                header_lines.append(f"# global: {line.strip()}")
        return "\n".join(header_lines)
    
    def _truncate_by_lines(self, content: str, max_lines: int = 150) -> str:
        lines = content.split('\n')
        if len(lines) <= max_lines:
            return content
        return "\n".join(lines[:max_lines]) + f"\n# ... ({len(lines) - max_lines} more lines)"
```

---

## 六、自动规模检测

```python
# 新文件: app/core/scalability_profile.py

from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class ScalabilityProfile:
    """按项目规模自动配置参数"""
    
    @classmethod
    def detect(cls, code_repo_path: str) -> Dict:
        """自动检测项目规模并返回配置"""
        root = Path(code_repo_path)
        code_extensions = {".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c"}
        
        file_count = 0
        total_lines = 0
        for ext in code_extensions:
            for f in root.rglob(f"*{ext}"):
                if f.is_file() and not any(x in str(f) for x in ["node_modules", ".git", "__pycache__"]):
                    file_count += 1
                    try:
                        total_lines += sum(1 for _ in f.open(encoding='utf-8', errors='replace'))
                    except Exception:
                        pass
        
        if file_count <= 20:
            profile = "SMALL"
            config = cls.SMALL
        elif file_count <= 200:
            profile = "MEDIUM"
            config = cls.MEDIUM
        elif file_count <= 2000:
            profile = "LARGE"
            config = cls.LARGE
        else:
            profile = "XLARGE"
            config = cls.XLARGE
        
        logger.info(f"Project: {file_count} files, {total_lines} lines → {profile} profile")
        return {**config, "_profile": profile, "_file_count": file_count, "_total_lines": total_lines}
    
    SMALL = {
        "max_agents": 50,
        "max_output_items": 30,
        "max_modifications": 30,
        "max_function_details": 30,
        "enable_module_partition": False,
        "enable_incremental": False,
        "enable_response_cache": False,
        "llm_max_qps": 5.0,
        "llm_max_concurrent": 3,
        "context_max_chars": 4000,
    }
    
    MEDIUM = {
        "max_agents_per_module": 50,
        "max_total_agents": 200,
        "max_module_summaries": 50,
        "max_file_summaries": 100,
        "max_function_details": 30,
        "max_modifications": 50,
        "enable_module_partition": True,
        "enable_incremental": False,
        "enable_response_cache": True,
        "llm_max_qps": 3.0,
        "llm_max_concurrent": 3,
        "context_max_chars": 6000,
    }
    
    LARGE = {
        "max_agents_per_module": 100,
        "max_total_agents": 500,
        "max_module_summaries": 100,
        "max_file_summaries": 200,
        "max_function_details": 50,
        "max_modifications": 100,
        "enable_module_partition": True,
        "enable_incremental": True,
        "enable_response_cache": True,
        "llm_max_qps": 3.0,
        "llm_max_concurrent": 5,
        "context_max_chars": 8000,
    }
    
    XLARGE = {
        "max_agents_per_module": 200,
        "max_total_agents": 1000,
        "max_module_summaries": 200,
        "max_file_summaries": 500,
        "max_function_details": 100,
        "max_modifications": 200,
        "enable_module_partition": True,
        "enable_incremental": True,
        "enable_response_cache": True,
        "enable_ast_cache": True,
        "enable_circuit_breaker": True,
        "llm_max_qps": 2.0,
        "llm_max_concurrent": 3,
        "context_max_chars": 10000,
    }
```

**在Pipeline启动时自动应用**:

```python
# neural_pipeline.py 修改

def execute_forward_pipeline(self, task_id, user_requirement, code_repo_path, max_iteration=5):
    # 自动检测项目规模
    profile = ScalabilityProfile.detect(code_repo_path)
    
    # 应用配置
    if profile.get("enable_module_partition"):
        partitioner = ModulePartitioner()
        modules = partitioner.partition(Path(code_repo_path))
        target_modules = partitioner.route_requirement(user_requirement, modules)
        # 仅分析目标模块的文件
        code_repo_path = target_modules  # 传入模块列表而非整个项目
    
    if profile.get("enable_incremental"):
        self._change_detector = ChangeDetector()
    
    # 配置LLM限频
    LLMRateLimiter.configure(
        max_qps=profile["llm_max_qps"],
        max_concurrent=profile["llm_max_concurrent"]
    )
    
    logger.info(f"Pipeline configured for {profile['_profile']} project ({profile['_file_count']} files)")
    
    # ... 正常执行pipeline
```

---

## 七、优化后数据流 (1M行代码)

```
用户需求 → Input
  ↓
[ModulePartitioner] 
  10000文件 → 80模块 → 需求路由选5模块 → 500文件
  ↓
[ChangeDetector]
  500文件 → 检测变更 → 首次全量, 后续增量(5%=25文件)
  ↓
Conv (分析500文件, 并发5, 限频3QPS)
  → 500个分析结果 (vs 原来20个)
  ↓
[HierarchicalCompressor]
  L1: 80模块摘要 (2000 tokens)
  L2: 200文件摘要 (6000 tokens)
  L3: 50函数详情 (4000 tokens)
  总计 ~12000 tokens, 在LLM窗口内
  ↓
FC1 [ModularSolutionPlanner]
  Step1: 模块选择(1次LLM, 输入=80模块摘要)
  Step2: 文件选择(1次LLM, 输入=200文件摘要)
  Step3: 函数规划(1次LLM, 输入=50函数详情)
  → 30-100项修改方案
  ↓
FC2 [DependencyGraph + SmartContext]
  拓扑排序 → 分3-5批次执行
  每批内: 不同文件并行, 同文件串行
  SmartContext: 目标函数不截断(6000 chars)
  → 30-100项修改, 无覆盖冲突
  ↓
FC3
  → 30-100个测试
  ↓
Output
  → Markdown报告
```

**耗时估算 (1M行代码)**:
| 阶段 | 耗时 | 说明 |
|------|------|------|
| ModulePartitioner | 5s | 文件遍历+目录分析 |
| ChangeDetector | 3s | hash比较(增量) |
| Conv (500文件) | 8min | 500/5并发×2s/文件 (限频3QPS) |
| Pool | 30s | 三级压缩+LLM |
| FC1 (3次LLM) | 3min | 模块→文件→函数 |
| FC2 (50修改) | 15min | 50/3并发×30s/修改 (限频3QPS) |
| FC3 (50测试) | 15min | 同上 |
| Output | 30s | jinja2渲染 |
| **总计** | **~43min** | |
| **迭代2-5轮(增量)** | **~3min/轮** | 仅重算变更文件 |
| **5轮总计** | **43 + 4×3 = 55min** | |

**vs 优化前30小时 → 优化后55分钟, 提升33倍**
