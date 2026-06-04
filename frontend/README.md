# AI 询价助手 - 前端

基于 Vue 3 + TypeScript + Vite 构建的 B 端采销 AI 询价系统前端。

## 技术栈

| 类别 | 技术 |
|---|---|
| 框架 | Vue 3.5 + Composition API + `<script setup>` |
| 语言 | TypeScript |
| 构建 | Vite 8 |
| UI | Element Plus 2 |
| 图表 | ECharts 6 |
| 状态管理 | Pinia 3 |
| HTTP | Axios + SSE 流式 |
| 语音 | Web Speech API |

## 本地开发

```bash
npm install
npm run dev              # 开发服务器 → http://localhost:3000
npm run build            # 生产构建 → dist/
```

## 构建与部署

前端通过 Docker 多阶段构建编译为 Nginx 静态资源，镜像推送到 Docker Hub：

```bash
# 项目根目录
bash scripts/build-push.sh   # 构建并推送前后端镜像
```

服务器通过 `docker compose pull && docker compose up -d` 拉取运行。

## 项目结构

```
frontend/
├── src/
│   ├── api/                  # API 封装
│   │   ├── request.ts        # Axios 实例 + 自动 token 续期
│   │   ├── chat.ts           # 流式对话 API
│   │   └── conversation.ts   # 对话 CRUD API
│   ├── components/chat/
│   │   ├── ChatInput.vue     # 输入框（含语音识别、思考模式开关）
│   │   └── MessageList.vue   # 消息列表（Markdown + 图表 + 产品链接）
│   ├── composables/
│   │   └── useSpeechRecognition.ts  # 语音识别封装
│   ├── stores/
│   │   └── chat.ts           # 多对话并行状态管理
│   ├── views/
│   │   ├── ChatView.vue      # 对话主页
│   │   ├── LoginView.vue     # 登录页
│   │   ├── AdminView.vue     # 管理后台布局
│   │   └── admin/            # 管理后台子页面
│   │       ├── DashboardPage.vue     # 数据概览
│   │       ├── ProductsPage.vue      # 商品管理
│   │       ├── ConversationsPage.vue # 对话记录
│   │       └── UsersPage.vue         # 用户管理
│   ├── router/index.ts       # 路由（含权限守卫）
│   └── types/message.ts      # 类型定义
├── nginx.conf.template        # Nginx 配置模板
├── Dockerfile                 # 多阶段构建
├── docker-compose.yml         # 前端栈编排
└── .env                       # 环境变量
```
