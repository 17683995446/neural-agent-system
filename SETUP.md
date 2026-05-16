# Neural Agent System - Quick Start

## 系统概述
类神经网络多Agent协作系统 - 基于深度学习架构思想的多Agent协同工作系统

## 快速启动

### 前置要求
- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ 可用内存

### 启动步骤

1. **克隆项目并进入目录**
   ```bash
   git clone <repo-url>
   cd neural-agent-system
   ```

2. **配置环境变量**
   ```bash
   cp backend/.env.example backend/.env
   # 编辑 .env 文件，添加你的 LLM API Keys
   ```

3. **一键启动**
   ```bash
   # Linux/Mac
   chmod +x start.sh
   ./start.sh

   # Windows (PowerShell)
   docker compose up -d
   ```

4. **验证服务**
   - 访问 http://localhost:8000/docs 查看API文档
   - 访问 http://localhost:3000 查看Grafana监控面板

## 核心服务

| 服务 | 端口 | 说明 |
|------|------|------|
| API Server | 8000 | FastAPI主服务 |
| RabbitMQ | 15672 | 消息队列管理 |
| Prometheus | 9090 | 监控指标 |
| Grafana | 3000 | 可视化监控 |
| Milvus | 9091 | 向量数据库 |
| Ray | 8265 | RL训练面板 |

## API使用示例

### 提交任务
```bash
curl -X POST http://localhost:8000/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-001",
    "user_requirement": "重构用户认证模块，添加JWT支持",
    "code_repo_url": "https://github.com/example/my-project",
    "target_branch": "main",
    "max_iteration": 5,
    "learning_rate": 0.1
  }'
```

### 查询任务
```bash
curl http://localhost:8000/api/v1/tasks/test-001
```

## 开发

### 本地开发环境
```bash
cd backend
pip install -e .
uvicorn app.main:app --reload
```

### 运行测试
```bash
cd backend
pytest tests/ -v
```

## 架构

```
输入层 → 卷积层 → 池化层 → 全连接层1 → 全连接层2 → 全连接层3 → 输出层
                                                                          ↓
                                                                    用户反馈
                                                                          ↓
                                                                    反向传播层
```

## 文档
- [技术文档](./类神经网络多Agent协作系统技术文档.md)
- [API文档](http://localhost:8000/docs)