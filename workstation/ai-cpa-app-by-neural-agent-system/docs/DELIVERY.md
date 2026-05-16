# AI智能CPA备考刷题网站 — 交付文档

## 项目概述
基于Neural Agent System的LLM能力，实现的AI CPA(注册会计师)备考刷题学习网站。

## 技术栈
- **后端**: FastAPI + SQLAlchemy + Pydantic V2 + JWT
- **前端**: Vue3 + Element Plus + ECharts + Pinia
- **AI引擎**: Neural Agent System CheapLLMClient → GLM-4-Flash
- **数据库**: SQLite (开发环境，可切换PostgreSQL)

## 项目目录
```
workstation/ai-cpa-app-by-neural-agent-system/
├── backend/              # FastAPI后端
│   ├── app/
│   │   ├── main.py       # 应用入口
│   │   ├── api/          # 6个API路由模块 (auth/questions/exam/ai/courses/orders)
│   │   ├── core/         # 核心模块 (config/security/database/llm)
│   │   ├── models/       # 9个数据模型
│   │   ├── services/     # 业务服务 (题库/初始化数据)
│   │   └── ai/           # 4个AI服务 (诊断/推荐/批改/答疑)
│   └── requirements.txt
├── frontend/             # Vue3前端
│   ├── src/
│   │   ├── views/        # 17个页面
│   │   ├── components/   # 6个组件
│   │   ├── stores/       # 3个Pinia store
│   │   ├── api/          # 6个API模块
│   │   └── router/       # 16条路由
│   └── package.json
└── docs/                 # 文档
```

## API端点 (27个)

### 认证 (4)
- POST /api/v1/auth/register — 注册
- POST /api/v1/auth/login — 登录
- GET  /api/v1/auth/me — 获取用户信息
- PUT  /api/v1/auth/me — 更新用户信息

### 题库 (4)
- GET  /api/v1/questions — 题目列表(支持筛选)
- GET  /api/v1/questions/count — 题目数量
- GET  /api/v1/questions/{id} — 题目详情
- POST /api/v1/questions — 添加题目

### 机考 (5)
- GET  /api/v1/exam/papers — 试卷列表
- GET  /api/v1/exam/papers/{id} — 试卷详情
- POST /api/v1/exam/papers/{id}/submit — 提交答卷
- GET  /api/v1/exam/results/{id} — 考试结果
- GET  /api/v1/exam/my-results — 我的成绩

### AI核心 (8)
- POST /api/v1/ai/diagnosis — 生成诊断试题
- POST /api/v1/ai/diagnosis/submit — 提交诊断结果
- GET  /api/v1/ai/recommend — 智能刷题推荐
- POST /api/v1/ai/grade — AI批改(客观+主观)
- POST /api/v1/ai/explain — AI题目解析
- POST /api/v1/ai/qa — AI答疑(RAG)
- POST /api/v1/ai/wrong-analysis — 错题归因
- GET  /api/v1/ai/study-plan — 个性化学习计划

### 课程 (4)
- GET  /api/v1/courses — 课程列表
- GET  /api/v1/courses/{id} — 课程详情
- POST /api/v1/courses/{id}/note — 添加笔记
- GET  /api/v1/courses/{id}/progress — 学习进度

### 订单 (3)
- POST /api/v1/orders — 创建订单
- GET  /api/v1/orders — 订单列表
- GET  /api/v1/orders/{id} — 订单详情

## 数据模型 (9个)
User, Question, StudyRecord, ExamPaper, ExamResult, Course, UserNote, Order, KnowledgeGraph

## 初始数据
- 20道CPA真题(覆盖6科: 会计/审计/财管/经济法/税法/战略)
- 4套模拟试卷
- 6门课程
- CPA知识点图谱

## 前端页面 (17个)
Home, Login, Register, Dashboard, Diagnosis, Practice, QuestionBank, ExamList, ExamTake, ExamResult, CourseList, CourseDetail, WrongBook, QA, Profile, Orders, StudyPlan

## 启动方式

### 后端
```bash
cd workstation/ai-cpa-app-by-neural-agent-system/backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```
API文档: http://localhost:9000/docs

### 前端
```bash
cd workstation/ai-cpa-app-by-neural-agent-system/frontend
npm install
npm run dev
```
访问: http://localhost:3000

## 集成测试结果

| 测试项 | 结果 |
|--------|------|
| 用户注册 | ✅ PASS |
| 用户登录 | ✅ PASS |
| 用户信息获取 | ✅ PASS |
| 题目查询(会计) | ✅ 6题返回 |
| 题目总数 | ✅ 20题 |
| 试卷列表 | ✅ 4套试卷 |
| 课程列表 | ✅ 6门课程 |
| AI智能推荐 | ✅ 返回推荐题目 |
| AI答疑(权责发生制) | ✅ 返回专业CPA答案 |
| AI批改(客观题) | ✅ 正确判定+踩分点 |
| AI解析 | ✅ 详细知识点梳理+解题思路 |

## 开源合规声明
- FastAPI (MIT) ✅
- SQLAlchemy (MIT) ✅
- Pydantic (MIT) ✅
- Vue3 (MIT) ✅
- Element Plus (MIT) ✅
- ECharts (Apache 2.0) ✅
- python-jose (MIT) ✅
- GLM-4-Flash (智谱AI免费商用) ✅

所有组件均为宽松许可(Apache 2.0/MIT)，无GPL/AGPL组件。
