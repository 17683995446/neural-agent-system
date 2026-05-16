# 100万行代码项目优化建议报告

**目标**: 将Neural Agent System从当前处理20文件/2分钟，扩展到处理10000文件/30分钟  
**现状瓶颈**: 1M行代码下覆盖率仅0.2%，总耗时~30小时(不可接受)

---

## 一、瓶颈总览

| 排名 | 瓶颈 | 当前值 | 1M行需求 | 差距 | 等级 |
|------|------|--------|---------|------|------|
| 1 | 卷积层文件截断 | 20文件 | 10000文件 | 500x | 致命 |
| 2 | 迭代全量重算 | 5×全量 | 仅算变更部分 | 5x | 严重 |
| 3 | 池化层信息截断 | 20项输出 | 需保留关键200+ | 10x | 严重 |
| 4 | LLM无限频保护 | 10并发直发 | 需QPS≤5 | - | 严重 |
| 5 | FC1上下文不足 | 15函数+10类 | 需看模块摘要 | 4000x | 高 |
| 6 | FC2无修改依赖图 | 50项并行 | 需拓扑排序 | - | 高 |
| 7 | 代码截断过激 | 80/60行 | 需智能摘要 | - | 高 |
| 8 | 无AST缓存 | 每次全量parse | 增量解析 | - | 中 |
| 9 | FC3覆盖率虚假 | 硬编码70% | 需实际测量 | - | 中 |
| 10 | 向量存储无分区 | 单collection | 按项目分区 | - | 中 |

---

## 二、优化方案 (按实施阶段)

### Phase 1: 架构解耦 — 分而治之 (核心，解决瓶颈1-3)

#### 2.1 项目分模块扫描

**问题**: 当前`max_agents=20`硬截断，10000文件只分析20个(覆盖率0.2%)

**方案**: 引入`ModulePartitioner`，将项目按目录/功能自动拆分为模块

```python
class ModulePartitioner:
    """项目模块自动拆分"""
    
    def partition(self, project_root: Path) -> List[Module]:
        """
        拆分策略（按优先级）:
        1. 按目录结构: src/api, src/core, src/models 各为一模块
        2. 按依赖图: 分析import关系，强连通分量为一模块  
        3. 按文件数上限: 每模块≤100文件，超出则继续拆分
        
        返回: List[Module], 每个Module包含:
        - name: 模块名
        - files: 文件列表
        - dependencies: 依赖的其他模块
        - entry_points: 模块入口文件
        """
```

**规模估算**:
- 1M行/10000文件 → 自动拆分为~50-100个模块
- 每模块100-200文件，含10-20个核心文件
- 用户需求自动路由到相关模块(基于关键词/路径匹配)
- 仅分析需求相关的3-5个模块 → 实际分析300-1000文件(覆盖率3-10%)

**配置变更**:
```python
ConvolutionConfig:
    max_agents_per_module = 50    # 每模块最多分析50文件
    max_total_agents = 500       # 总计最多分析500文件
    enable_module_partition = True
```

#### 2.2 增量变更检测

**问题**: 每次迭代全量重算，5次迭代=5×全量耗时

**方案**: 引入`ChangeDetector`，只重算变更部分

```python
class ChangeDetector:
    """增量变更检测"""
    
    def __init__(self):
        self._ast_cache = ASTCache()      # AST解析缓存
        self._file_hashes = {}             # 文件内容hash
        self._last_analysis = {}           # 上次分析结果
    
    def detect_changes(self, project_root: Path) -> ChangeSet:
        """
        检测变更:
        1. 文件级: hash比较，找出新增/修改/删除的文件
        2. 函数级: AST diff，找出修改的函数/类
        3. 影响级: 分析修改函数的调用链，标记受影响的函数
        
        返回: ChangeSet包含:
        - changed_files: 变更文件列表
        - changed_symbols: 变更符号列表  
        - affected_symbols: 受影响符号列表
        - unchanged_analysis: 可复用的上次分析结果
        """
    
    def compute_incremental_analysis(self, changes: ChangeSet) -> AnalysisResult:
        """
        增量分析:
        1. 复用unchanged_analysis中未变更文件的结果
        2. 仅对changed_files重新调用LLM分析
        3. 仅对affected_symbols重新计算相关性
        
        节省: 假设每次迭代只改5%文件，则节省95%的卷积层耗时
        """
```

**规模估算**:
- 首次: 全量分析(无法避免)
- 后续迭代: 假设每次改5%文件 → 卷积层耗时降为5%
- 5次迭代总耗时: 1x + 4×0.05x = 1.2x (vs 当前5x，节省76%)

#### 2.3 层次化压缩

**问题**: 池化层`max_output_items=20`，10000文件信息大量丢失

**方案**: 三级压缩架构

```python
class HierarchicalCompressor:
    """三级压缩"""
    
    def compress(self, analysis_results: List) -> CompressedOutput:
        """
        L1 - 模块级摘要 (保留所有模块):
            每模块生成一段摘要(50字)，共50-100条
            用于: FC1理解项目全貌
            
        L2 - 文件级摘要 (保留相关模块的所有文件):
            按相关性排序，保留top200文件的基础信息
            (文件名+函数签名列表，不含函数体)
            
        L3 - 函数级详情 (仅保留最相关的):
            按相关性top50函数的完整签名+docstring
            用于: FC2生成具体修改
        """
```

**配置变更**:
```python
PoolingConfig:
    max_module_summaries = 100     # L1: 保留所有模块摘要
    max_file_summaries = 200       # L2: 保留相关文件摘要
    max_function_details = 50      # L3: 保留最相关函数详情
    enable_hierarchical = True
```

---

### Phase 2: LLM调用优化 (解决瓶颈4-5)

#### 2.4 令牌桶限频器 + 请求队列

**问题**: 10线程并发直发LLM请求，频繁429超时

**方案**: 全局`LLMRateLimiter`单例

```python
import asyncio
import time
import threading

class LLMRateLimiter:
    """全局LLM调用限频器"""
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, max_qps: float = 3.0, max_concurrent: int = 5):
        self._max_qps = max_qps          # 每秒最多3个请求
        self._max_concurrent = max_concurrent  # 最多5个并发
        self._semaphore = threading.Semaphore(max_concurrent)
        self._tokens = max_qps
        self._last_refill = time.time()
        self._lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_qps=3.0, max_concurrent=5)
        return cls._instance
    
    def acquire(self):
        """获取调用许可(阻塞等待)"""
        self._semaphore.acquire()  # 限制并发
        with self._lock:
            now = time.time()
            self._tokens = min(
                self._max_qps,
                self._tokens + (now - self._last_refill) * self._max_qps
            )
            self._last_refill = now
            if self._tokens < 1:
                wait = (1 - self._tokens) / self._max_qps
                time.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1
    
    def release(self):
        self._semaphore.release()
```

在`LLMClient.complete()`中使用:
```python
limiter = LLMRateLimiter.get_instance()
limiter.acquire()
try:
    response = self._make_request(messages, **kwargs)
finally:
    limiter.release()
```

#### 2.5 Circuit Breaker

**问题**: LLM服务故障时持续重试，浪费资源

```python
class CircuitBreaker:
    """熔断器"""
    CLOSED = "closed"       # 正常
    OPEN = "open"           # 熔断(拒绝请求)
    HALF_OPEN = "half_open" # 半开(允许1个请求试探)
    
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self._state = self.CLOSED
        self._failures = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time = 0
    
    def call(self, func, *args, **kwargs):
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time > self._recovery_timeout:
                self._state = self.HALF_OPEN
            else:
                raise CircuitOpenError("LLM circuit breaker is open")
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

#### 2.6 LLM响应缓存

**问题**: 相同prompt重复调用LLM

```python
class LLMResponseCache:
    """LLM响应缓存(基于prompt hash)"""
    
    def __init__(self, ttl_seconds=3600, max_size=1000):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
    
    def get_or_call(self, messages: list, llm_func, **kwargs) -> Any:
        key = self._make_key(messages, kwargs)
        cached = self._get(key)
        if cached is not None:
            logger.debug(f"LLM cache hit: {key[:16]}...")
            return cached
        result = llm_func(messages, **kwargs)
        self._put(key, result)
        return result
    
    def _make_key(self, messages, kwargs):
        content = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()
```

#### 2.7 FC1分模块规划

**问题**: FC1 prompt只含15函数+10类，1M行项目10万+函数完全看不到

**方案**: 分层规划

```python
class ModularSolutionPlanner:
    """分模块方案规划"""
    
    def plan(self, requirement, module_summaries, relevant_files):
        """
        Step 1 - 模块级规划 (1次LLM调用):
            输入: 需求 + 所有模块摘要(50-100条，每条50字≈5000字)
            输出: 需要修改的模块列表 + 每模块修改目标
            
        Step 2 - 文件级规划 (每模块1次LLM调用):
            输入: 需求 + 模块内文件摘要(文件名+签名列表)
            输出: 需要修改的文件列表 + 每文件修改目标
            
        Step 3 - 函数级规划 (每文件1次LLM调用):
            输入: 需求 + 文件完整代码(智能截断)
            输出: 具体修改方案(与当前FC1相同格式)
        """
```

**LLM调用量估算**:
- Step 1: 1次 (模块选择)
- Step 2: 3-5次 (选中的模块)
- Step 3: 10-30次 (选中的文件)
- 总计: 14-36次 (vs 当前1次但几乎无用的规划)

---

### Phase 3: 修改执行优化 (解决瓶颈6-7)

#### 2.8 修改依赖图

**问题**: FC2的50项修改并行执行，同一文件多次修改互相覆盖

**方案**: 构建修改依赖图，拓扑排序执行

```python
class ModificationDependencyGraph:
    """修改依赖图"""
    
    def build(self, modifications: List[Dict]) -> List[List[Dict]]:
        """
        构建依赖图并拓扑排序:
        
        规则:
        1. 同一文件的修改 → 必须串行(按行号排序)
        2. 文件A的修改依赖文件B的类型 → B先改
        3. 无依赖的修改 → 可并行
        
        返回: List[List[Dict]] - 分层执行计划
        - 外层List: 执行批次(串行)
        - 内层List: 同批次可并行的修改
        - 同文件的修改保证在同一批次中串行
        """
    
    def apply_sequential_for_same_file(self, modifications: List[Dict]):
        """
        同文件串行修改:
        第2次修改基于第1次修改的结果(而非原始代码)
        """
```

#### 2.9 智能代码上下文

**问题**: FC2/FC3截断到80/60行，大函数完全无法理解

**方案**: 智能上下文窗口

```python
class SmartContextWindow:
    """智能代码上下文"""
    
    def get_context(self, file_path: Path, target_symbol: str, max_chars=4000) -> str:
        """
        智能截断策略:
        1. 定位目标符号(函数/类)的AST节点
        2. 提取目标符号完整定义(不截断!)
        3. 提取目标符号的直接依赖(调用的函数签名)
        4. 提取类定义(如果目标是方法)
        5. 提取import语句
        6. 剩余空间填充文件头部的全局变量和注释
        
        优先级: imports > 目标符号完整定义 > 类定义 > 依赖签名 > 全局变量
        硬保证: 目标符号定义永远不被截断
        """
```

---

### Phase 4: 基础设施优化 (解决瓶颈8-10)

#### 2.10 AST缓存 + 增量解析

```python
class ASTCache:
    """AST解析缓存"""
    
    def __init__(self, cache_dir=".cache/ast"):
        self._cache_dir = Path(cache_dir)
        self._memory_cache = {}  # file_hash -> ast_tree
    
    def parse(self, file_path: Path) -> ast.AST:
        file_hash = self._hash_file(file_path)
        if file_hash in self._memory_cache:
            return self._memory_cache[file_hash]
        
        cache_file = self._cache_dir / f"{file_hash}.ast"
        if cache_file.exists():
            tree = pickle.loads(cache_file.read_bytes())
        else:
            tree = ast.parse(file_path.read_text(encoding='utf-8'))
            cache_file.write_bytes(pickle.dumps(tree))
        
        self._memory_cache[file_hash] = tree
        return tree
```

#### 2.11 实际覆盖率测量

```python
class CoverageRunner:
    """实际运行pytest+coverage测量覆盖率"""
    
    def measure(self, project_root: Path, test_dir: Path) -> CoverageReport:
        """
        执行: pytest --cov=project_root --cov-report=json test_dir/
        返回: CoverageReport(含行覆盖率、分支覆盖率、未覆盖行)
        
        用于:
        1. FC3生成测试后验证实际覆盖率
        2. 反向传播中将覆盖率作为奖励信号
        3. 迭代中判断是否需要补充测试
        """
```

#### 2.12 向量存储分区

```python
class PartitionedVectorStore:
    """分区向量存储"""
    
    def __init__(self):
        # collection命名: agent_memories_{project_hash}_{agent_type}
        pass
    
    def save(self, project_id: str, agent_type: str, content: str, metadata: dict):
        collection = self._get_collection(f"memories_{project_id}_{agent_type}")
        collection.add(documents=[content], metadatas=[metadata])
    
    def retrieve(self, project_id: str, agent_type: str, query: str, top_k=5):
        collection = self._get_collection(f"memories_{project_id}_{agent_type}")
        return collection.similarity_search_with_score(query, k=top_k)
```

---

## 三、优化后性能预估

### 1M行代码 (10000文件) 优化前后对比

| 指标 | 优化前 | 优化后 | 提升倍数 |
|------|--------|--------|---------|
| **分析文件数** | 20 (0.2%覆盖) | 300-500 (3-5%覆盖) | 15-25x |
| **卷积层耗时** | ~5.5h (全量) | ~15min (分模块+增量) | 22x |
| **池化层信息保留** | 20项 | 模块摘要100+文件摘要200+函数详情50 | 7x |
| **FC1可见上下文** | 25个符号 | 100模块+500文件签名+50函数详情 | 13x |
| **FC2修改正确率** | 低(同文件覆盖) | 高(依赖图+串行) | - |
| **LLM调用成功率** | ~60%(限频) | ~95%(令牌桶+熔断) | - |
| **单次Pipeline耗时** | ~6h | ~30min | 12x |
| **5次迭代总耗时** | ~30h | ~50min (增量) | 36x |
| **内存峰值** | ~500MB | ~200MB (流式+缓存) | 2.5x |

### 可行性判定

| 项目规模 | 优化前 | 优化后 |
|---------|--------|--------|
| 小 (1-10文件) | ✅ 2-5min | ✅ 2-5min (无变化) |
| 中 (10-100文件) | ⚠️ 5-15min | ✅ 5-10min |
| 大 (100-1000文件) | ⚠️ 15-60min | ✅ 15-30min |
| 超大 (1000-10000文件) | ❌ 数小时 | ✅ 30-60min |
| **1M行 (10000文件)** | ❌ 30h | ✅ **50min** |

---

## 四、实施路线图

```
Phase 1 (2周) — 架构解耦,解决致命瓶颈
├── 2.1 ModulePartitioner (项目分模块)
├── 2.2 ChangeDetector (增量变更检测)  
├── 2.3 HierarchicalCompressor (三级压缩)
└── 配置化所有硬编码数值

Phase 2 (1周) — LLM调用优化
├── 2.4 LLMRateLimiter (令牌桶限频)
├── 2.5 CircuitBreaker (熔断器)
├── 2.6 LLMResponseCache (响应缓存)
└── 2.7 ModularSolutionPlanner (分模块规划)

Phase 3 (1周) — 修改执行优化
├── 2.8 ModificationDependencyGraph (依赖图)
├── 2.9 SmartContextWindow (智能上下文)
└── 代码截断策略重构

Phase 4 (1周) — 基础设施
├── 2.10 ASTCache (解析缓存)
├── 2.11 CoverageRunner (实际覆盖率)
├── 2.12 PartitionedVectorStore (分区存储)
└── 性能基准测试套件

总计: ~5周
```

---

## 五、配置化方案

将所有硬编码限制改为可配置，支持按项目规模自动调整：

```python
class ScalabilityProfile:
    """按项目规模自动配置"""
    
    @classmethod
    def auto_detect(cls, file_count: int) -> Dict:
        if file_count <= 20:      # 小项目
            return cls.SMALL
        elif file_count <= 200:   # 中项目
            return cls.MEDIUM
        elif file_count <= 2000:  # 大项目
            return cls.LARGE
        else:                     # 超大项目
            return cls.XLARGE
    
    SMALL = {
        "max_agents": 50,
        "max_output_items": 30,
        "max_modifications": 30,
        "enable_module_partition": False,
        "enable_incremental": False,
        "llm_max_qps": 5,
        "llm_max_concurrent": 3,
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
        "llm_max_qps": 3,
        "llm_max_concurrent": 3,
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
        "llm_max_qps": 3,
        "llm_max_concurrent": 5,
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
        "llm_max_qps": 2,          # 更保守
        "llm_max_concurrent": 3,   # 更保守
        "enable_response_cache": True,
        "enable_ast_cache": True,
        "enable_circuit_breaker": True,
    }
```

在Pipeline启动时自动检测:
```python
file_count = len(list(Path(code_repo_path).rglob("*.py")))
profile = ScalabilityProfile.auto_detect(file_count)
logger.info(f"Project scale: {file_count} files, using {profile} profile")
```
