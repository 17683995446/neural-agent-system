# 类神经网络多Agent协作系统

## 项目结构
```
neural-agent-system/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/v1/endpoints/  # API端点
│   │   ├── core/              # 核心配置
│   │   ├── models/            # 数据模型
│   │   ├── services/          # 业务服务层
│   │   │   ├── input_layer/   # 输入层
│   │   │   ├── convolution/   # 卷积层
│   │   │   ├── pooling/       # 池化层
│   │   │   ├── fullconnect/   # 全连接层
│   │   │   ├── output/        # 输出层
│   │   │   └── backward/      # 反向传播层
│   │   ├── agents/            # Agent核心单元
│   │   │   ├── memory/        # 记忆模块
│   │   │   └── trust/         # 信任度管理
│   │   └── utils/             # 工具函数
│   ├── tests/                 # 测试文件
│   ├── scripts/               # 脚本
│   └── docker/                # Docker配置
├── task_output/               # 任务输出目录
└── code_repos/                # 代码仓库目录
```

## 技术栈
- FastAPI + Pydantic (API层)
- AutoGen + CrewAI (Agent编排)
- SWE-agent + Aider (代码处理)
- LangChain (上下文处理)
- LiteLLM (LLM适配)
- Ray RLlib (反向传播)
- Redis (短期记忆)
- Milvus/Chroma (长期记忆)
- PostgreSQL (元数据存储)
- RabbitMQ (消息队列)