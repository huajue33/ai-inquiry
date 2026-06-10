# 部署指南

## 架构概览

```
用户 → 宝塔 Nginx (:80/:443) ──── SSL 终止
  └── /  → 127.0.0.1:3010 → quotation-frontend (容器内 Nginx + Vue)
                              └── /api → backend:8000 → quotation-backend (FastAPI)
                                                         ├── Meilisearch (容器)
                                                         └── MySQL 8.0 (宿主机)
```

单入口架构：宝塔只反代到前端容器；前端容器内的 Nginx 负责静态资源，并把 `/api`（含 SSE / WebSocket）通过 docker 网络用服务名 `backend:8000` 转发给后端容器。

| 服务 | 镜像 | 端口 |
|---|---|---|
| meilisearch | `getmeili/meilisearch:v1.11` | 内部 7700 |
| backend | `ai-inquiry-backend:latest`（本地构建） | 127.0.0.1:8090 → 容器 8000 |
| frontend | `ai-inquiry-frontend:latest`（本地构建） | 3010 → 容器 80 |

三个服务由根目录 `docker-compose.yml` 统一编排，`docker compose up -d` 一次启动。

- **域名**：`ai-inquiry.huahub.com.cn`
- **服务器**：`117.72.207.28`（国内，无法访问 Docker Hub）
- **环境要求**：Docker Engine 20.10+、Compose V2、MySQL 8.0+

---

## 一、部署方案：本地构建 + 镜像导出 + rsync 传输

由于服务器在国内、无法拉取 Docker Hub 镜像，采用「本地构建 → `docker save` 导出 tar → rsync 传到服务器 → `docker load` 加载 → 重启容器」的离线方案。一条命令完成：

```
本地开发机                                       服务器（117.72.207.28）
─────────                                       ──────────────────────
docker build  (前后端镜像)
  │
docker save   (导出 .tar)
  │
rsync 增量压缩传输  ───────────────────────────▶  接收 .tar
  │
ssh 远程执行  ─────────────────────────────────▶  git pull
                                                  docker load < *.tar
                                                  docker compose up -d   (全部服务)
                                                  docker image prune -f
```

- **构建在本地**：避免服务器 2 核 2G 编译压力
- **传输用 rsync**：增量 + 压缩，比 scp 省流量
- **无需 Docker Hub / 无需 CI**：整个流程由 `deploy.sh` 一键驱动

---

## 二、准备工作

### 2.1 本地环境

需要本地能运行 `docker`、`rsync`、`ssh`（Windows 建议用 Git Bash 或 WSL；确保已安装 rsync）。

### 2.2 部署配置

复制配置模板并填入服务器信息：

```bash
cp .deploy.env.example .deploy.env
```

`.deploy.env` 内容：

| 变量 | 说明 | 值 |
|---|---|---|
| `SERVER_IP` | 服务器 IP | `117.72.207.28` |
| `SERVER_USER` | SSH 用户名 | `root` |
| `SERVER_PORT` | SSH 端口 | `22` |
| `SERVER_DIR` | 服务器项目目录 | `/www/wwwroot/ai-inquiry` |

> `.deploy.env` 已在 `.gitignore` 中忽略，不会提交。

建议配置 SSH 免密登录（`ssh-copy-id`），否则每次部署会多次提示输入密码。

### 2.3 服务器初始化（仅首次）

```bash
# 克隆仓库
git clone <仓库地址> /www/wwwroot/ai-inquiry

# 配置后端环境变量（含数据库密码等敏感信息）
cp /www/wwwroot/ai-inquiry/.env.example /www/wwwroot/ai-inquiry/.env
vim /www/wwwroot/ai-inquiry/.env

# 前端无需 .env：地址/端口已写死在 nginx.conf 和 deploy.sh 中
```

### 2.4 环境变量

**后端 `.env` 必填项**：

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key |
| `DB_PASSWORD` | MySQL 密码 |
| `DB_NAME` | 数据库名 |
| `MEILI_MASTER_KEY` | Meilisearch 密钥（≥16 字符） |
| `JWT_SECRET` | JWT 签名密钥 |

**前端**：无需环境变量。后端地址（docker 网络服务名 `http://backend:8000`）写死在 `frontend/nginx.conf`，对外端口（3010）由 `docker-compose.yml` 的 `WEB_PORT` 控制（默认 3010）。

---

## 三、一键部署

本地项目根目录执行：

```bash
bash deploy.sh
```

脚本会自动完成：构建前后端镜像 → 导出 tar → rsync 传输 → 远程 `git pull` + `docker load` + 重启两套栈 + 清理。

### 验证

```bash
# 后端
curl http://127.0.0.1:8090/api/health   # {"status":"ok"}

# 前端
curl http://127.0.0.1:3010               # 返回 HTML

# 通过域名
curl http://ai-inquiry.huahub.com.cn
```

---

## 四、配置宝塔 Nginx（首次）

宝塔 → 网站 → 添加站点 `ai-inquiry.huahub.com.cn` → 配置文件：

```nginx
# WebSocket 升级映射（放在 server 块外，http 上下文）
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name ai-inquiry.huahub.com.cn;

    client_max_body_size 20m;

    # 全部反代到前端容器，由前端容器内的 nginx 再转发 /api 到后端
    location / {
        proxy_pass http://127.0.0.1:3010;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支持 WebSocket（实时语音）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # 支持 SSE（流式输出）
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    access_log /www/wwwlogs/ai-inquiry.huahub.com.cn.log;
    error_log  /www/wwwlogs/ai-inquiry.huahub.com.cn.error.log;
}
```

> 宝塔不再需要单独配 `/api/` 和 WebSocket 的 location —— 这些都由前端容器内的 nginx（`frontend/nginx.conf`）处理。宝塔只把整个站点转给 3010 即可。

---

## 五、日常更新

### 改了代码（前端或后端）

```bash
# 本地一键部署即可（会重新构建并传输镜像）
bash deploy.sh
```

如需同时同步代码到 git：

```bash
git add . && git commit -m "描述改动"   # 按需 push
bash deploy.sh
```

### 仅改环境变量

直接在服务器修改 `.env` 后重启，无需重新构建镜像：

```bash
vim /www/wwwroot/ai-inquiry/.env
docker compose up -d
```

---

## 六、运维命令

```bash
# 查看容器状态
docker ps

# 查看资源占用
docker stats --no-stream

# 查看日志
docker compose logs -f backend          # 后端
docker compose logs -f meilisearch      # 搜索引擎
docker compose logs -f frontend         # 前端

# 重启服务
docker compose restart backend
docker compose restart frontend         # 前端

# 重建搜索索引
docker compose exec backend python sync_products.py --reset

# 停止服务
docker compose down                      # 全部（保留数据）

# 停止并清空 Meilisearch 数据（危险）
docker compose down -v
```

---

## 七、常见问题

**Q: 本地没有 rsync（Windows）**

用 Git Bash 时可通过包管理器安装 rsync，或改用 WSL。也可临时把 `deploy.sh` 里的 rsync 行换成 `scp -P ${SERVER_PORT}`。

**Q: 每次部署反复要输入密码**

配置 SSH 免密：`ssh-copy-id -p 22 root@117.72.207.28`。

**Q: 前端报 502 / 504**

- 检查后端是否运行：`docker compose ps`、`docker compose logs backend`
- 从前端容器内测试到后端的连通性：`docker compose exec frontend wget -qO- http://backend:8000/api/health`

**Q: docker load 后容器没更新**

`docker compose up -d` 会识别镜像变化并重建。若没生效，先 `docker compose up -d --force-recreate`。

**Q: 端口冲突**

- 80 端口被宝塔 Nginx 占用 → 前端容器用 3010
- 宝塔网站设为「纯静态」，关闭 PHP 以释放内存

**Q: 采购员查询提示"无权限"**

管理后台 → 用户管理 → 数据权限 → 勾选对应的二级分类。

**Q: Meilisearch 数据丢失**

不要使用 `docker compose down -v`（`-v` 会删除 volume）。普通 `down`/`restart` 是安全的。

**Q: Token 过期白屏**

- Refresh token 会自动续期（7 天有效）
- 过期后自动跳转登录页
- 检查浏览器 localStorage 中的 `refresh_token`
