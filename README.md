# AI 询价助手

基于对话式交互的 B 端采销 AI 询价系统，用户通过自然语言提问，AI 返回结构化的价格信息、趋势分析和比价结果。

## 功能特性

### 核心功能
- **自然语言询价** — 输入产品名称即可查询最新价格
- **价格趋势分析** — 查看产品近期价格走势和涨跌排行
- **智能比价** — 多品牌、多品质横向对比
- **模糊搜索** — 支持 Meilisearch 全文检索，中文分词、同义词、容错匹配
- **深度思考模式** — 可选开启 AI 推理过程，获得更深入的分析

### 对话体验
- **流式输出** — SSE 实时推送，逐字显示回复
- **工具调用可视化** — 展示 AI 正在调用哪些工具
- **上下文记忆** — 支持多轮对话，AI 理解追问意图
- **对话历史** — 自动保存，支持切换和恢复
- **多对话并行** — 切换对话不中断正在运行的请求

### 管理后台
- **数据概览** — 用户数、商品数、对话数、Token 消耗统计图表
- **商品管理** — 搜索、分类筛选、查看历史价格（ECharts 图表）
- **对话记录** — 查看所有用户对话详情、Token 消耗明细
- **用户管理** — 新建用户、角色分配、启用/禁用、重置密码

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python) |
| AI 框架 | LangChain + Agent + Tool Calling |
| LLM | 阿里云百炼 (通义千问 qwen3.5-plus) |
| 搜索引擎 | Meilisearch（中文分词、同义词、容错） |
| 数据库 | MySQL + SQLAlchemy 2.0 |
| 前端框架 | Vue 3 + TypeScript + Vite |
| UI 组件 | Element Plus |
| 图表 | ECharts |
| 状态管理 | Pinia |
| 认证 | JWT (python-jose + bcrypt) |

## 项目结构

```
├── backend/                    # 后端
│   ├── app/
│   │   ├── api/                # API 路由
│   │   │   ├── auth.py         # 认证（登录、修改密码）
│   │   │   ├── chat.py         # 对话（流式/非流式）
│   │   │   ├── conversation.py # 对话管理（CRUD）
│   │   │   └── admin.py        # 管理后台 API
│   │   ├── core/
│   │   │   ├── prompts.py      # 系统提示词
│   │   │   └── security.py     # JWT + 密码加密
│   │   ├── models/             # ORM 模型
│   │   ├── services/
│   │   │   ├── ai_service.py   # LangChain Agent + 流式输出
│   │   │   ├── price_service.py # 价格查询（Meilisearch + MySQL）
│   │   │   ├── search_service.py # Meilisearch 管理
│   │   │   └── title_service.py  # 对话标题生成（轻量模型）
│   │   ├── tools/              # LangChain 工具
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   └── main.py             # FastAPI 入口
│   ├── sync_products.py        # 产品数据同步到 Meilisearch
│   ├── generate_prices.py      # 模拟价格数据生成
│   └── requirements.txt
├── frontend/                   # 前端
│   ├── src/
│   │   ├── api/                # API 请求封装
│   │   ├── components/chat/    # 对话组件
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── views/              # 页面
│   │   │   ├── ChatView.vue    # 对话主页
│   │   │   ├── LoginView.vue   # 登录页
│   │   │   ├── AdminView.vue   # 管理后台布局
│   │   │   └── admin/          # 管理后台子页面
│   │   └── router/             # 路由
│   └── package.json
└── docker-compose.yml          # Meilisearch 容器
```

## 快速开始

### 环境要求
- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Docker（用于 Meilisearch）

### 1. 启动 Meilisearch

```bash
docker-compose up -d
```

### 2. 配置后端

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入你的百炼 API Key 和数据库密码
```

`.env` 配置项：
```env
DASHSCOPE_API_KEY=sk-your-api-key
DASHSCOPE_MODEL=qwen3.5-plus
DASHSCOPE_LITE_MODEL=qwen-turbo
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-password
DB_NAME=quotation
MEILI_URL=http://127.0.0.1:7700
MEILI_MASTER_KEY=your-master-key
JWT_SECRET=your-jwt-secret
```

### 3. 安装后端依赖并启动

```bash
pip install -r requirements.txt
python sync_products.py --reset   # 同步产品数据到 Meilisearch
uvicorn app.main:app --reload --port 8000
```

### 4. 安装前端依赖并启动

```bash
cd frontend
npm install
npm run dev
```

### 5. 访问

- 前端：http://localhost:5173
- 后端 API 文档：http://localhost:8000/docs
- 默认管理员账号：`admin` / `admin123`

## 数据库

### 表结构
- **products** — 10194 个产品（品名、品牌、规格、品质、分类）
- **prices** — 每日价格记录（支持向后填充）
- **categories** — 三级分类体系（2 个一级 → 24 个二级 → 242 个三级）
- **users** — 用户（admin/manager/buyer 三种角色）
- **conversations** — 对话列表（支持逻辑删除）
- **chat_messages** — 对话消息（含 Token 消耗统计）

## API 接口

| Method | Path | 说明 |
|--------|------|------|
| POST | /api/auth/login | 登录 |
| POST | /api/auth/change-password | 修改密码 |
| POST | /api/chat/stream | 流式对话（SSE） |
| GET | /api/conversations/ | 对话列表 |
| POST | /api/conversations/message | 保存消息 |
| GET | /api/admin/stats | 管理后台统计 |
| GET | /api/admin/products | 商品列表 |
| GET | /api/admin/conversations | 所有对话记录 |
| GET | /api/admin/users | 用户列表 |

## 架构设计

```
Vue3 前端 ──SSE──▶ FastAPI 后端 ──▶ LangChain Agent ──▶ 通义千问 (百炼)
                         │                    │
                         ▼                    ▼
                      MySQL              Tool Calling
                         │                    │
                         ▼                    ▼
                   Meilisearch          价格查询/趋势/比价
```

## License

MIT
