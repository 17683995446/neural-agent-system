# Neural Agent System - 修改建议书

**基于**: VERIFICATION_REPORT.md 验证结果  
**审计发现**: 43个问题 (高15 / 中22 / 低6)  
**日期**: 2026-05-02  

---

## 优先级说明

| 级别 | 含义 | 修复时限 |
|------|------|----------|
| P0-紧急 | 影响正确性/安全性，可导致数据破坏或崩溃 | 立即 |
| P1-重要 | 影响性能/可靠性，可导致功能降级 | 本迭代 |
| P2-一般 | 影响可维护性/可观测性 | 下迭代 |
| P3-建议 | 改善体验/代码质量 | 排期 |

---

## 一、P0-紧急 (5项)

### 1.1 [P0] 修复 `complete()` 重试耗尽后 `raise None` 崩溃

**文件**: `app/core/llm_client.py:126-165`  
**问题**: 所有重试都进入429/5xx分支时，`last_error` 始终为 `None`，循环结束后 `raise last_error` 抛出 `TypeError`  
**影响**: LLM限频时系统崩溃而非优雅降级  
**修改方案**:

```python
# llm_client.py complete() 方法中
_RETRY_STATUS_CODES = {429, 500, 502, 503, 529}

last_error = None
for attempt in range(self.max_retries):
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=(10, self.timeout))
        if response.status_code == 200:
            try:
                self._update_usage(response.json())
            except Exception as e:
                logger.debug(f"Usage update skipped: {e}")
            return response.json()
        elif response.status_code in _RETRY_STATUS_CODES:
            last_error = requests.exceptions.HTTPError(
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
            wait = (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"LLM retry {attempt+1}/{self.max_retries} after {wait:.1f}s (HTTP {response.status_code})")
            time.sleep(wait)
            continue
        else:
            raise requests.exceptions.HTTPError(f"HTTP {response.status_code}: {response.text[:200]}")
    except requests.exceptions.RequestException as e:
        last_error = e
        if attempt < self.max_retries - 1:
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
            continue

# 确保 last_error 不为 None
if last_error is None:
    last_error = requests.exceptions.RequestException("All retry attempts failed with no specific error")
raise last_error
```

### 1.2 [P0] 修复 async/sync 混用阻塞事件循环

**文件**: `app/api/v1/endpoints/*.py`, `app/services/pipeline/neural_pipeline.py`  
**问题**: `async def` 端点内调用同步阻塞方法(含 `requests.post`)，阻塞整个事件循环，所有并发请求被串行化  
**影响**: 生产环境下并发能力为零  
**修改方案** (两种选择，推荐方案A):

**方案A — 端点改为 `def`** (最小改动，FastAPI自动在线程池运行):
```python
# pipeline.py
@router.post("/execute", response_model=PipelineExecuteResponse)
def execute_pipeline(request: PipelineExecuteRequest):  # async def → def
    pipeline = get_pipeline_service()
    result = pipeline.execute_forward_pipeline(...)
    return result
```

**方案B — Service改为async** (更彻底，长线推荐):
```python
# llm_client.py 新增 async complete_async()，使用 aiohttp
# 各 service 方法改为 async def
# pipeline 改为 async
# 端点保持 async def
```

### 1.3 [P0] 修复反向传播硬编码初始权重导致学习无效

**文件**: `app/agents/trust/backward.py:200`  
**问题**: `current_weights = {upper_id: 1.0 for upper_id in agents}` 每次反向传播从默认值1.0开始，之前的学习结果完全丢失  
**影响**: 反向传播机制形同虚设，信任度更新无法累积  
**修改方案**:

```python
# backward.py propagate_feedback() 中
async def propagate_feedback(self, task_id, feedback, agents):
    # 从 TrustManager 读取当前权重，而非硬编码
    try:
        trust_matrix = self.trust_manager.get_trust_matrix(task_id)
        current_weights = {}
        for agent_id in agents:
            trust_record = trust_matrix.get(agent_id, {})
            current_weights[agent_id] = trust_record.get("trust_value", 1.0)
    except Exception as e:
        logger.warning(f"Failed to load trust weights from DB, using defaults: {e}")
        current_weights = {upper_id: 1.0 for upper_id in agents}
    
    # ... 后续梯度计算逻辑不变
```

### 1.4 [P0] 修复 FC2 模板 fallback 写入破坏性内容

**文件**: `app/services/fullconnect/service_fc2.py:138-163`  
**问题**: `_generate_modification_template()` 返回的 `modified_code` 仅为一行注释 `# Modified {target} - {action}`，如果写入文件会完全覆盖源代码  
**影响**: LLM不可用时，执行代码修改会破坏用户源文件  
**修改方案**:

```python
def _generate_modification_template(self, original_code: str, modification: dict) -> dict:
    """Fallback: 在原始代码中添加注释标记，而非替换为注释"""
    target = modification.get("target", "unknown")
    action = modification.get("action", "modify")
    
    # 保留原始代码，仅在顶部添加变更标记
    marker = f"# [NeuralAgent] TODO: {action} {target} (LLM fallback - manual review required)\n"
    modified_code = marker + original_code
    
    return {
        "target": target,
        "action": action,
        "modified_code": modified_code,
        "diff": f"[FALLBACK] {action} on {target} - marked for manual review",
        "generated_by": "template",
        "requires_manual_review": True  # 标记需要人工审核
    }
```

同时在 `_apply_single_modification` 中：
```python
if modification.get("requires_manual_review"):
    logger.warning(f"Skipping file write for template fallback: {modification['target']} - requires manual review")
    return modification  # 不写入文件
```

### 1.5 [P0] 修复 CORS 安全漏洞

**文件**: `app/main.py:16-22`  
**问题**: `allow_origins=["*"]` + `allow_credentials=True` 允许任何域携带凭证发起请求  
**影响**: CSRF攻击风险  
**修改方案**:

```python
# config.py 新增
allowed_cors_origins: str = "http://localhost:3000,http://localhost:8080"

# main.py
allowed = [o.strip() for o in settings.allowed_cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 二、P1-重要 (10项)

### 2.1 [P1] 统一 JSON 提取逻辑，消除6处重复

**文件**: convolution/service.py, pooling/service.py, service_fc1.py, service_fc2.py, service_fc3.py, backward/service.py  
**问题**: `json_str.split("```json")[1].split("```")[0]` 模式重复6次，且 `IndexError` 未处理  
**修改方案**: 新建 `app/core/llm_utils.py`:

```python
"""LLM 工具函数"""
import json
import re
import logging
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def extract_json_from_llm_response(
    text: str,
    schema: Optional[Type[BaseModel]] = None,
    fallback: Any = None,
) -> Any:
    """
    从LLM响应中提取JSON，支持多种格式：
    1. ```json ... ``` 代码块
    2. ``` ... ``` 代码块
    3. 裸JSON字符串
    
    Args:
        text: LLM响应文本
        schema: 可选的Pydantic模型用于验证
        fallback: 解析失败时的返回值
    
    Returns:
        解析后的dict/list，或fallback
    """
    if not text or not text.strip():
        return fallback
    
    text = text.strip()
    json_str = None
    
    # 策略1: 提取 ```json ... ``` 或 ``` ... ``` 代码块
    code_block_pattern = re.compile(r'```(?:json)?\s*\n(.*?)\n```', re.DOTALL)
    match = code_block_pattern.search(text)
    if match:
        json_str = match.group(1).strip()
    
    # 策略2: 尝试整个文本作为JSON
    if json_str is None:
        # 移除可能的 markdown 前缀
        cleaned = re.sub(r'^[^{\[]*', '', text)
        cleaned = re.sub(r'[^}\]]*$', '', cleaned)
        json_str = cleaned
    
    # 解析JSON
    try:
        result = json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"JSON parse failed: {e}, text preview: {text[:100]}")
        return fallback
    
    # Schema验证
    if schema is not None:
        try:
            validated = schema.model_validate(result)
            return validated.model_dump()
        except ValidationError as e:
            logger.warning(f"Schema validation failed: {e}")
            return fallback
    
    return result


def truncate_code(content: str, max_chars: int = 8000, max_lines: int = 200) -> str:
    """截断过长代码，保留头部和尾部"""
    if len(content) <= max_chars:
        lines = content.split('\n')
        if len(lines) <= max_lines:
            return content
        head = '\n'.join(lines[:max_lines // 2])
        tail = '\n'.join(lines[-max_lines // 2:])
        return f"{head}\n... (truncated {len(lines) - max_lines} lines) ...\n{tail}"
    
    return content[:max_chars] + f"\n... (truncated, total {len(content)} chars) ..."
```

各Agent替换为：
```python
from app.core.llm_utils import extract_json_from_llm_response, truncate_code

result = extract_json_from_llm_response(text, schema=MySchema, fallback=default_value)
```

### 2.2 [P1] 抽象 LLM 调用+JSON解析+降级为统一方法

**文件**: `app/core/llm_client.py`  
**问题**: 8个Agent重复 "check available → build prompt → complete → extract → parse → fallback" 模式  
**修改方案**: 在 `LLMClient` 上添加 `complete_json()` 方法：

```python
def complete_json(
    self,
    messages: list[dict],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    schema: Optional[Type[BaseModel]] = None,
    fallback: Any = None,
    agent_name: str = "unknown",
) -> Any:
    """
    发送LLM请求并解析JSON响应，失败时返回fallback。
    封装了重试、JSON提取、schema验证和降级逻辑。
    """
    if not self.is_available:
        logger.info(f"[{agent_name}] LLM unavailable, using fallback")
        return fallback
    
    try:
        response = self.complete(messages=messages, temperature=temperature, max_tokens=max_tokens)
        text = self.get_response_text(response)
        if not text:
            logger.warning(f"[{agent_name}] LLM returned empty response")
            return fallback
        return extract_json_from_llm_response(text, schema=schema, fallback=fallback)
    except Exception as e:
        logger.warning(f"[{agent_name}] LLM call failed: {e}, using fallback")
        return fallback
```

各Agent简化为：
```python
result = self.llm_client.complete_json(
    messages=[{"role": "user", "content": prompt}],
    schema=SolutionSchema,
    fallback=self._fallback_method(),
    agent_name="fc1",
)
```

### 2.3 [P1] 修复 `acomplete()` 重试逻辑与同步方法不一致

**文件**: `app/core/llm_client.py:199-230`  
**问题**: 异步方法 `except Exception as e` 是bare catch，429和5xx应重试但其他异常也盲目重试  
**修改方案**:

```python
async def acomplete(self, messages, **kwargs):
    last_error = None
    async with aiohttp.ClientSession() as session:  # session提到循环外
        for attempt in range(self.max_retries):
            try:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data
                    elif resp.status in _RETRY_STATUS_CODES:
                        last_error = Exception(f"HTTP {resp.status}")
                        await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
                        continue
                    else:
                        raise Exception(f"HTTP {resp.status}: {await resp.text()[:200]}")
            except aiohttp.ClientError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
                    continue
    
    if last_error is None:
        last_error = Exception("All async retry attempts failed")
    raise last_error
```

### 2.4 [P1] 修复 `iteration_manager.py` `forward_time_ms` 始终为0

**文件**: `app/services/pipeline/iteration_manager.py:80-82`  
**问题**: `t = time.time(); state.forward_time_ms = (t - t) * 1000` 计算 `t - t = 0`  
**修改方案**:

```python
def complete_forward(self, iteration_id: str, result: dict, start_time: float):
    state = self._iterations.get(iteration_id)
    if state:
        state.forward_time_ms = (time.time() - start_time) * 1000
        state.forward_result = result
        state.status = "forward_completed"
```

调用处：
```python
forward_start = time.time()
result = pipeline.execute_forward_pipeline(...)
iteration_mgr.complete_forward(iter_id, result, forward_start)
```

### 2.5 [P1] Pipeline 层失败传播机制

**文件**: `app/services/pipeline/neural_pipeline.py:95-141`  
**问题**: 上层失败返回 `{"error": ...}` 后，下游层静默拿到空数据继续执行，无明确失败状态传播  
**修改方案**:

```python
def execute_forward_pipeline(self, task_input):
    layer_errors = []
    
    # 卷积层
    try:
        conv_output = conv_service.analyze_files(...)
    except Exception as e:
        conv_output = {"error": str(e), "task_id": task_id}
        layer_errors.append(("convolution", str(e)))
    
    # 检查上层是否有error，标记partial failure
    if layer_errors:
        logger.warning(f"Pipeline partial failure: {layer_errors}")
    
    # 池化层 - 如果上游完全失败则跳过
    if conv_output.get("error") and not conv_output.get("analyzed_files"):
        pool_output = {"error": "Skipped: upstream convolution failed", "task_id": task_id}
        layer_errors.append(("pooling", "skipped: upstream failed"))
    else:
        # ... 正常执行
    
    # 最终结果包含错误信息
    return {
        ...,
        "pipeline_status": "partial_failure" if layer_errors else "success",
        "layer_errors": layer_errors,
    }
```

### 2.6 [P1] 修复 TrustManager DB session 线程安全问题

**文件**: `app/agents/trust/manager.py:17-18`  
**问题**: 长期持有的DB session在ThreadPoolExecutor下不安全  
**修改方案**:

```python
class TrustManager:
    def __init__(self, db_session=None):
        self._external_session = db_session  # 仅在外部传入时使用
    
    def _get_session(self):
        """每次操作获取新session"""
        if self._external_session:
            return self._external_session
        return SessionLocal()
    
    def get_trust_matrix(self, task_id: str):
        db = self._get_session()
        try:
            return db.query(TrustModel).filter_by(task_id=task_id).all()
        finally:
            if not self._external_session:
                db.close()
```

### 2.7 [P1] 修复路径遍历安全风险

**文件**: `app/services/input_layer/service.py:99-114`  
**问题**: `local_code_path` 直接传给 `shutil.copytree`，无路径验证  
**修改方案**:

```python
from pathlib import Path

ALLOWED_BASE_DIRS = [Path("D:/claude_workspace").resolve()]

def _validate_path(self, local_path: str) -> Path:
    """验证路径在允许范围内，防止路径遍历"""
    resolved = Path(local_path).resolve()
    for base in ALLOWED_BASE_DIRS:
        try:
            resolved.relative_to(base)
            return resolved
        except ValueError:
            continue
    raise ValueError(f"Path '{local_path}' is outside allowed directories")
```

### 2.8 [P1] API key 安全存储

**文件**: `.env`, `.gitignore`  
**问题**: API密钥明文存储在 `.env` 中，可能被提交到git  
**修改方案**:
1. 确保 `.gitignore` 包含 `.env`
2. 创建 `.env.example` 仅包含占位符：
```env
ANTHROPIC_AUTH_TOKEN=your-token-here
ANTHROPIC_BASE_URL=https://your-api-base-url
ANTHROPIC_MODEL=MiniMax-M2.5
LITELLM_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
```
3. 启动时检查关键key是否为占位符，是则拒绝启动

### 2.9 [P1] `complete()` model参数临时替换需用 try/finally

**文件**: `app/core/llm_client.py:122-159`  
**问题**: 异常路径下 `self.model` 可能不被恢复  
**修改方案**:

```python
def complete(self, messages, model=None, **kwargs):
    original_model = self.model
    if model:
        self.model = model
    try:
        # ... 重试循环 ...
        pass
    finally:
        self.model = original_model
```

### 2.10 [P1] DB session 在 Pipeline 中使用 context manager

**文件**: `app/services/pipeline/neural_pipeline.py:41-51`  
**问题**: `db.close()` 不在 finally 中，异常时连接泄漏  
**修改方案**:

```python
def _update_task_status(self, task_id: str, status: str):
    with SessionLocal() as db:
        task = db.query(TaskModel).filter_by(task_id=task_id).first()
        if task:
            task.status = status
            db.commit()
```

---

## 三、P2-一般 (10项)

### 3.1 [P2] 完善健康检查端点

**文件**: `app/main.py:42-44`  
**修改方案**:

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/health/detail")
async def health_detail():
    checks = {}
    
    # LLM
    from app.core.llm_client import get_llm_client
    llm = get_llm_client()
    checks["llm"] = {"available": llm.is_available, "model": llm.model}
    
    # DB
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = {"status": "connected"}
    except Exception as e:
        checks["database"] = {"status": "unavailable", "error": str(e)[:100]}
    
    all_healthy = all(c.get("available", c.get("status") == "connected") for c in checks.values())
    return {"status": "healthy" if all_healthy else "degraded", "checks": checks}
```

### 3.2 [P2] 添加 LLM 连接测试端点

**文件**: `app/api/v1/endpoints/pipeline.py`  
**修改方案**:

```python
@router.get("/llm/test")
async def test_llm_connection():
    from app.core.llm_client import get_llm_client
    llm = get_llm_client()
    if not llm.is_available:
        return {"status": "unavailable", "reason": "API key not configured"}
    try:
        result = llm.test_llm_connection()
        return {"status": "connected", "model": llm.model, "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}
```

### 3.3 [P2] 添加降级指标收集器

**文件**: 新建 `app/core/metrics.py`  
**修改方案**:

```python
"""降级指标收集"""
from collections import defaultdict
from datetime import datetime
import threading

class DegradationMetrics:
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._counts = defaultdict(int)
        self._reasons = defaultdict(list)
        self._lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def record_fallback(self, agent_name: str, reason: str):
        with self._lock:
            key = f"{agent_name}:{reason}"
            self._counts[key] += 1
            self._reasons[key].append(datetime.now().isoformat())
    
    def get_summary(self) -> dict:
        with self._lock:
            return {k: {"count": v, "last_5": self._reasons[k][-5:]} for k, v in self._counts.items()}
```

### 3.4 [P2] 单例模式添加线程安全

**文件**: 所有 `get_xxx_service()` 函数  
**修改方案**: 统一使用 `threading.Lock`:

```python
_service_lock = threading.Lock()
_service_instance = None

def get_service():
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = Service()
    return _service_instance
```

### 3.5 [P2] FC2 prompt 语言标记动态化

**文件**: `app/services/fullconnect/service_fc2.py:85-89`  
**修改方案**:

```python
def _detect_language(self, file_path: str) -> str:
    ext_map = {".py": "python", ".js": "javascript", ".ts": "typescript", 
               ".java": "java", ".go": "go", ".rs": "rust", ".cpp": "cpp", ".c": "c"}
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext, "")

# prompt中使用
lang = self._detect_language(target_file)
prompt = f"原始代码: ```{lang}\n{content}\n```"
```

### 3.6 [P2] 代码语法验证使用 `ast.parse()` 替代括号匹配

**文件**: `app/services/fullconnect/service_fc2.py:374-378`  
**修改方案**:

```python
def verify_syntax(self, code: str, language: str = "python") -> bool:
    if language == "python":
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            logger.warning(f"Syntax error in generated code: {e}")
            return False
    else:
        # 非Python语言，回退到括号匹配
        return self._basic_bracket_check(code)
```

### 3.7 [P2] CoverageAnalyzer 标注为估算值

**文件**: `app/services/fullconnect/service_fc3.py:193-194`  
**修改方案**:

```python
# 将硬编码 0.7 改为可配置参数，并在结果中标注
estimated_coverage_ratio = 0.7  # TODO: 接入 coverage.py 获取真实覆盖率
covered_lines += int(len(lines) * estimated_coverage_ratio)

# 结果中标注
result["coverage_type"] = "estimated"
result["coverage_note"] = "Coverage is estimated, not measured. Run tests with coverage.py for actual results."
```

### 3.8 [P2] Prompt 注入防护

**文件**: 所有Agent prompt构建处  
**修改方案**:

```python
def sanitize_user_input(text: str, max_length: int = 10000) -> str:
    """清理用户输入，减少prompt注入风险"""
    if len(text) > max_length:
        text = text[:max_length]
    # 移除可能的指令注入模式
    patterns = [
        r"(?i)ignore\s+(above|previous|all)\s+instructions",
        r"(?i)disregard\s+(all|previous)",
        r"(?i)you\s+are\s+now",
        r"(?i)system\s*:",
    ]
    for p in patterns:
        text = re.sub(p, "[FILTERED]", text)
    return text
```

### 3.9 [P2] Milvus URL 配置一致性

**文件**: `app/agents/memory/long_term.py:40`  
**修改方案**:

```python
from app.core.config import settings

def get_vector_store():
    # 从settings解析Milvus连接参数
    milvus_url = settings.milvus_url  # e.g. "http://localhost:19530"
    parsed = urlparse(milvus_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 19530
    
    _vector_store = Milvus(
        embedding_function=embeddings,
        connection_args={"host": host, "port": port},
        ...
    )
```

### 3.10 [P2] `.env.example` 与 Settings 字段对齐

**文件**: `.env.example`  
**修改方案**:
```env
# Neural Agent System Configuration
APP_NAME=Neural Agent System
DEBUG=true

# LLM Configuration
ANTHROPIC_AUTH_TOKEN=your-token-here
ANTHROPIC_BASE_URL=https://your-api-base-url:8443
ANTHROPIC_MODEL=MiniMax-M2.5
LITELLM_API_KEY=your-key-here
LITELLM_API_BASE=
LITELLM_MODEL=
OPENAI_API_KEY=your-key-here
DEFAULT_LLM_MODEL=MiniMax-M2.5

# Infrastructure
REDIS_URL=redis://localhost:6379/0
POSTGRES_URL=postgresql://user:pass@localhost:5432/neural_agent
RABBITMQ_URL=amqp://user:pass@localhost:5672/
MILVUS_URL=http://localhost:19530

# Trust & Learning
MAX_ITERATION=5
DEFAULT_LEARNING_RATE=0.1
TRUST_INITIAL_VALUE=1.0
TRUST_MIN_VALUE=0.0
TRUST_MAX_VALUE=2.0

# CORS
ALLOWED_CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

---

## 四、P3-建议 (5项)

### 4.1 [P3] 添加 LLM Client mock 单元测试

**文件**: 新建 `tests/test_llm_client.py`  
**修改方案**: 测试用例覆盖：
- `complete()` 正常返回
- `complete()` 429重试3次后抛异常
- `complete()` 5xx重试
- `complete()` 非重试状态码直接抛异常
- `complete()` `last_error` 不为None保证
- `acomplete()` 重试逻辑
- `extract_json_from_llm_response()` 各种格式
- `complete_json()` fallback逻辑
- `is_available` 检测
- 超时处理

### 4.2 [P3] 添加 API 层集成测试

**文件**: 新建 `tests/test_api_integration.py`  
**修改方案**: 使用 `httpx.AsyncClient` + `asgi_lifespan` 测试HTTP端点

### 4.3 [P3] Input层 prompt 添加 few-shot 示例

**文件**: `app/services/input_layer/service.py:34-41`  
**修改方案**: 添加输出格式要求和示例，使LLM输出更可控

### 4.4 [P3] 区分 connect/read 超时

**文件**: `app/core/llm_client.py:104`  
**修改方案**: `timeout=(10, self.timeout)` — 10s连接，120s读取

### 4.5 [P3] 添加任务取消/删除 API

**文件**: `app/api/v1/endpoints/input_layer.py`  
**修改方案**: 添加 `DELETE /tasks/{task_id}` 和 `POST /tasks/{task_id}/cancel`

---

## 五、修改影响矩阵

| 修改项 | 影响文件数 | 影响测试 | 向后兼容 | 风险 |
|--------|-----------|---------|----------|------|
| 1.1 complete()重试 | 1 | 需更新mock | ✅ | 低 |
| 1.2 async/sync | 8+ | 需全量回归 | ⚠️ 端点签名 | 中 |
| 1.3 反向传播权重 | 1 | 需更新 | ✅ | 低 |
| 1.4 FC2 fallback | 1 | 需更新 | ✅ | 低 |
| 1.5 CORS | 1 | 无 | ⚠️ 需配置 | 低 |
| 2.1 统一JSON提取 | 6→1 | 简化 | ✅ | 低 |
| 2.2 complete_json | 8→8 | 简化 | ✅ | 低 |
| 2.3 acomplete修复 | 1 | 需更新 | ✅ | 低 |
| 2.4 forward_time | 2 | 需更新 | ✅ | 低 |
| 2.5 Pipeline错误传播 | 1 | 需更新 | ⚠️ 返回结构 | 中 |
| 2.6 TrustManager | 1 | 需更新 | ✅ | 中 |
| 2.7 路径验证 | 1 | 需新增 | ✅ | 低 |

---

## 六、建议修复顺序

```
Phase 1 (P0 - 立即修复，约2小时):
  1.1 complete() raise None → 保证不崩溃
  1.2 async/sync → 方案A(端点改def)，10分钟
  1.3 反向传播权重 → 学习结果有效
  1.4 FC2 fallback → 防止文件破坏
  1.5 CORS → 安全基线

Phase 2 (P1 - 本迭代，约4小时):
  2.1 统一JSON提取 → llm_utils.py
  2.2 complete_json() → 简化8个Agent
  2.3 acomplete修复 → 异步可靠性
  2.4 forward_time_ms → 指标正确
  2.5 Pipeline错误传播 → 可观测性
  2.6 TrustManager线程安全 → 并发安全
  2.7 路径验证 → 安全
  2.8 API key安全 → 安全
  2.9 model try/finally → 正确性
  2.10 DB context manager → 资源安全

Phase 3 (P2 - 下迭代，约3小时):
  3.1-3.10 全部P2项

Phase 4 (P3 - 排期):
  4.1-4.5 测试补充和优化
```

---

## 七、总结

| 优先级 | 数量 | 预计工时 | 核心收益 |
|--------|------|----------|----------|
| P0 | 5 | 2h | 消除崩溃/数据破坏/安全漏洞 |
| P1 | 10 | 4h | 统一架构/消除重复/增强可靠性 |
| P2 | 10 | 3h | 可观测性/可维护性/安全加固 |
| P3 | 5 | 2h | 测试覆盖/代码质量 |
| **合计** | **30** | **11h** | |

**核心结论**: 系统功能验证全部通过，但存在5个P0级问题(崩溃风险+安全漏洞+数据破坏)需立即修复。P1级问题(代码重复+异步一致性+线程安全)应在本迭代内完成。完成后系统将从"功能可用"升级为"生产可靠"。
