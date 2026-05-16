# Neural Agent System - 用户使用指南

## 快速开始

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置LLM

编辑 `backend/.env`，填入你的LLM API信息：

```env
ANTHROPIC_AUTH_TOKEN=你的API密钥
ANTHROPIC_BASE_URL=https://你的API地址
ANTHROPIC_MODEL=模型名称
```

> 系统兼容任何OpenAI格式API（如OpenAI、MiniMax、DeepSeek等）

### 3. 启动服务

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

打开浏览器访问 `http://localhost:8000/docs` 可查看交互式API文档。

---

## 两种使用方式

### 方式A：一键执行（最简单）

提交需求，系统自动走完整个Pipeline并返回结果：

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/execute \
  -H "Content-Type: application/json" \
  -d '{
    "user_requirement": "为所有函数添加错误处理和类型注解",
    "local_code_path": "/path/to/your/project/src"
  }'
```

**参数说明**：
| 参数 | 必填 | 说明 |
|------|------|------|
| `user_requirement` | ✅ | 你的需求描述，越详细越好 |
| `local_code_path` | 二选一 | 本地代码目录路径 |
| `code_repo_url` | 二选一 | Git仓库URL |
| `max_iteration` | 否 | 最大迭代轮数，默认5 |

**执行流程**：Input → Conv → Pool → FC1 → FC2 → FC3 → Output → 返回结果

---

### 方式B：迭代式执行（可逐步改进）

适合需要人工审核、逐步优化的场景：

**第1步：启动迭代**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/start-iteration \
  -H "Content-Type: application/json" \
  -d '{
    "user_requirement": "重构配置模块，支持多环境配置",
    "local_code_path": "/path/to/your/project",
    "max_iteration": 3
  }'
```

**第2步：查看结果，提交反馈**
```bash
curl -X POST http://localhost:8000/api/v1/pipeline/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "上一步返回的task_id",
    "satisfaction_score": 4,
    "feedback_items": [
      {"type": "positive", "description": "错误处理添加正确"},
      {"type": "negative", "description": "边界情况未覆盖"}
    ],
    "comments": "请补充None值检查"
  }'
```

**反馈规则**：
| satisfaction_score | 行为 |
|---|---|
| 1-2 | 不满意，继续迭代改进 |
| 3 | 一般，继续迭代 |
| 4-5 | 满意/非常满意，停止迭代 |

也可以设置 `"stop_iteration": true` 强制停止。

**第3步（可选）：查看迭代状态**
```bash
curl http://localhost:8000/api/v1/pipeline/iteration/{task_id}
```

---

## 其他API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/health/detail` | GET | 详细状态（LLM/DB连通性） |
| `/api/v1/pipeline/status/{task_id}` | GET | 查询任务状态 |
| `/api/v1/pipeline/iterations` | GET | 列出所有迭代会话 |
| `/api/v1/pipeline/stop/{task_id}` | POST | 强制停止迭代 |
| `/api/v1/pipeline/backward` | POST | 单独执行反向传播 |

---

## 不启动服务直接调用（Python脚本）

```python
from app.services.pipeline.neural_pipeline import get_neural_pipeline

pipeline = get_neural_pipeline()

# 一键执行
result = pipeline.execute_forward_pipeline(
    task_id="my_task_001",
    user_requirement="为所有函数添加错误处理和日志记录",
    code_repo_path="/path/to/your/code",
    max_iteration=1
)

print(result["status"])            # "completed"
print(result["execution_time_ms"]) # 耗时
print(result["layer_outputs"])     # 各层输出
```

---

## 输出说明

执行完成后，结果保存在 `task_output/{task_id}/` 目录：

```
task_output/my_task_001/
├── convolution/    # 代码分析结果
├── pooling/        # 特征压缩结果
├── fullconnect/    # 方案+代码修改+测试
└── output/
    └── task_report.md  # 📄 最终报告（Markdown）
```

---

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANTHROPIC_AUTH_TOKEN` | 无 | LLM API密钥（必填） |
| `ANTHROPIC_BASE_URL` | - | LLM API地址 |
| `ANTHROPIC_MODEL` | MiniMax-M2.5 | 模型名称 |
| `MAX_ITERATION` | 5 | 默认最大迭代轮数 |
| `ALLOWED_CORS_ORIGINS` | localhost:3000,8080 | CORS白名单 |
| `MAX_CONCURRENT_MODS` | 8 | FC2并发修改数 |
| `MAX_CONCURRENT_TESTS` | 8 | FC3并发测试生成数 |

> 💡 如果LLM限频严重，将 `MAX_CONCURRENT_MODS` 和 `MAX_CONCURRENT_TESTS` 设为 2
