# AI 询价助手

基于对话式交互的 B 端采销 AI 询价系统，用户通过自然语言提问，AI 返回结构化的价格信息、趋势分析和比价结果。

## 在线体验

🔗 **体验地址**：[http://ai-inquiry.huahub.com.cn/](http://ai-inquiry.huahub.com.cn/)

| 账号 | 姓名 | 角色 | 密码 |
|------|------|------|------|
| admin | 管理员 | 管理员 | 123456 |
| test | 测试 | 主管 | 123456 |
| test001 | 采购人员 | 采购员 | 123456 |

> 不同角色拥有不同的数据权限和功能权限，可分别登录体验。

## 功能特性

### 核心功能
- **自然语言询价** — 输入产品名称即可查询最新价格
- **价格趋势分析** — 查看产品近期价格走势和涨跌排行
- **智能比价** — 多品牌、多品质横向对比
- **模糊搜索** — 支持 Meilisearch 全文检索，中文分词、同义词、容错匹配
- **深度思考模式** — 可选开启 AI 推理过程，获得更深入的分析
- **产品名可点击** — AI 回复中的产品名可点击查看详情和历史价格图表

### 对话体验
- **流式输出** — SSE 实时推送，逐字显示回复
- **工具调用可视化** — 展示 AI 正在调用哪些工具
- **上下文记忆** — 支持多轮对话，AI 理解追问意图
- **对话历史** — 自动保存，支持切换和恢复
- **多对话并行** — 切换对话不中断正在运行的请求
- **语音输入** — 按住说话，松开发送（Web Speech API）

### 管理后台
- **数据概览** — 用户数、商品数、对话数、Token 消耗统计图表
- **商品管理** — 搜索、分类筛选、查看历史价格（ECharts 图表）
- **对话记录** — 关键词搜索、用户筛选、查看对话详情和 Token 消耗
- **用户管理** — 新建用户、角色分配、启用/禁用、重置密码
- **数据权限** — 按二级分类授权，采购员只能查询被授权分类的产品价格

### 安全机制
- **Refresh Token** — 双 token 机制，access token 短期有效 + refresh token 自动续期
- **角色权限** — admin / manager / buyer 三级角色，功能和数据分离
- **分类级数据隔离** — 采购员仅可查询被授权的产品分类

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | FastAPI (Python 3.11) |
| AI 框架 | LangChain 0.3 + Agent + Tool Calling |
| LLM | 阿里云百炼 (通义千问 qwen3.5-plus / qwen-turbo) |
| 搜索引擎 | Meilisearch 1.11（中文分词、同义词、容错） |
| 数据库 | MySQL 8.0 + SQLAlchemy 2.0 |
| 前端框架 | Vue 3.5 + TypeScript + Vite 8 |
| UI 组件 | Element Plus 2 |
| 图表 | ECharts 6 |
| 状态管理 | Pinia 3 |
| 认证 | JWT (python-jose + bcrypt) + Refresh Token |
| 部署 | Docker + Nginx 反代 |

## 项目结构

```
├── backend/                    # 后端
│   ├── app/
│   │   ├── api/                # API 路由
│   │   │   ├── auth.py         # 认证（登录、刷新token、修改密码）
│   │   │   ├── chat.py         # 对话（流式/非流式）
│   │   │   ├── conversation.py # 对话管理（CRUD + 自动标题）
│   │   │   └── admin.py        # 管理后台 API
│   │   ├── core/
│   │   │   ├── prompts.py      # 系统提示词
│   │   │   ├── security.py     # JWT + Refresh Token + 密码加密
│   │   │   └── permissions.py  # 角色权限 + 数据权限（分类级）
│   │   ├── models/             # ORM 模型
│   │   ├── services/
│   │   │   ├── ai_service.py   # LangChain Agent + 流式 + 思考模式
│   │   │   ├── price_service.py # 价格查询（Meilisearch + MySQL）
│   │   │   ├── search_service.py # Meilisearch 索引管理
│   │   │   └── title_service.py  # 对话标题生成（轻量模型）
│   │   ├── tools/              # LangChain 工具（查价/趋势/排行/比价/追问）
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   └── main.py             # FastAPI 入口
│   ├── migrations/             # 数据库迁移脚本
│   ├── sync_products.py        # 产品数据同步到 Meilisearch
│   ├── generate_prices.py      # 模拟价格数据生成
│   └── requirements.txt
├── frontend/                   # 前端
│   ├── src/
│   │   ├── api/                # API 请求封装（含自动续期）
│   │   ├── components/chat/    # 对话组件（输入框 + 消息列表）
│   │   ├── composables/        # 语音识别 composable
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── views/              # 页面
│   │   │   ├── ChatView.vue    # 对话主页
│   │   │   ├── LoginView.vue   # 登录页
│   │   │   ├── AdminView.vue   # 管理后台布局
│   │   │   └── admin/          # 管理后台子页面
│   │   └── router/             # 路由（含权限守卫）
│   └── package.json
├── docker-compose.yml          # 全栈编排（Meilisearch + Backend + Frontend）
├── deploy.sh                   # 本地构建 + 导出镜像 + rsync 传输 + 远程部署
├── .deploy.env.example         # 部署配置模板（服务器 IP / 用户 / 目录）
├── DEPLOY.md                   # 详细部署文档
└── README.md
```

## 快速开始（本地开发）

### 环境要求
- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Docker Desktop

### 1. 启动 Meilisearch

```bash
docker compose up -d meilisearch
```

### 2. 配置后端

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入百炼 API Key、数据库密码等
pip install -r requirements.txt
python sync_products.py --reset   # 同步产品数据到 Meilisearch
uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 访问

- 前端：http://localhost:3000
- 后端 API 文档：http://localhost:8000/docs

## 数据库

### 表结构
- **products** — 10194 个产品（品名、品牌、规格、品质、分类）
- **prices** — 每日价格记录（支持向后填充）
- **categories** — 三级分类体系（2 个一级 → 24 个二级 → 242 个三级）
- **users** — 用户（admin/manager/buyer 三种角色）
- **conversations** — 对话列表（支持逻辑删除）
- **chat_messages** — 对话消息（含 Token 消耗统计）
- **user_category_permissions** — 用户-分类权限映射

## API 接口

| Method | Path | 说明 |
|--------|------|------|
| POST | /api/auth/login | 登录（返回 access + refresh token） |
| POST | /api/auth/refresh | 刷新 token |
| POST | /api/auth/change-password | 修改密码 |
| GET | /api/auth/me | 当前用户信息 |
| POST | /api/chat/stream | 流式对话（SSE） |
| GET | /api/conversations/ | 对话列表 |
| POST | /api/conversations/message | 保存消息 |
| GET | /api/admin/stats | 管理后台统计 |
| GET | /api/admin/products | 商品列表（支持 ID/名称搜索） |
| GET | /api/admin/products/:id/prices | 商品历史价格 |
| GET | /api/admin/conversations | 对话记录（支持关键词/用户筛选） |
| GET | /api/admin/users | 用户列表 |
| PUT | /api/admin/users/:id/permissions | 设置用户数据权限 |

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                          │
│  ChatView ──SSE──▶ API Layer ──axios──▶ /api/*              │
│  AdminView                    (自动 refresh token 续期)      │
└────────────────────────────┬────────────────────────────────┘
                             │ Nginx 反代
┌────────────────────────────▼────────────────────────────────┐
│                     后端 (FastAPI)                            │
│  ┌─────────┐    ┌──────────────┐    ┌───────────────────┐   │
│  │ Auth    │    │ LangChain    │    │ Admin API         │   │
│  │ JWT +   │    │ Agent        │    │ 统计/商品/对话/用户│   │
│  │ Refresh │    │ + Tools      │    └───────────────────┘   │
│  └─────────┘    └──────┬───────┘                            │
│                         │ Tool Calling                        │
│              ┌──────────▼──────────┐                         │
│              │ 查价/趋势/排行/比价  │                         │
│              └──────────┬──────────┘                         │
│                         │                                    │
│         ┌───────────────┼───────────────┐                    │
│         ▼               ▼               ▼                    │
│    Meilisearch      MySQL          通义千问 (百炼)            │
│    (模糊搜索)    (价格/产品/用户)   (LLM 推理)               │
└─────────────────────────────────────────────────────────────┘
```

## 部署

> 详细文档见 [DEPLOY.md](./DEPLOY.md)

### 架构

```
用户 → 宝塔 Nginx (:80, SSL)
  ├── /     → 127.0.0.1:3010  (前端 Docker 容器)
  └── /api/ → 127.0.0.1:8090  (后端 Docker 容器)
```

### 部署流程

```
本地开发 → docker build → docker save (.tar)
                ↓
         rsync 传输到国内服务器（免 Docker Hub）
                ↓
         ssh: docker load + docker compose up -d  ← 一键完成
```

- **一键部署**：本地 `bash deploy.sh`，自动构建、导出、rsync 传输、远程加载并重启
- **离线方案**：服务器在国内无法访问 Docker Hub，镜像本地构建后通过 rsync 传输
- **前端**：容器内 Nginx 提供静态资源，外层宝塔 Nginx 处理 `/api/` 反代、域名和 SSL
- **数据库**：MySQL 8.0 运行在宿主机，通过 `host.docker.internal` 连接

### 服务器手动部署

```bash
cd /www/wwwroot/ai-inquiry
docker load < ai-inquiry-backend.tar && docker load < ai-inquiry-frontend.tar
docker compose up -d                                  # 一次启动全部服务
docker image prune -f
```

## License

MIT
