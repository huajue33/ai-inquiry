# Docker 部署指南（前后端分离）

## 拓扑

```
┌──────────────────────────┐         ┌────────────────────────────────┐
│  Web 服务器              │  HTTPS  │  API 服务器                    │
│                          │ ──────▶ │                                │
│  ┌────────────────────┐ │         │  ┌────────┐  ┌──────────────┐  │
│  │ frontend (Nginx)   │ │         │  │backend │──│ mysql        │  │
│  │  反代 /api → 后端 │ │         │  │FastAPI │  └──────────────┘  │
│  └────────────────────┘ │         │  │        │  ┌──────────────┐  │
│                          │         │  │        │──│ meilisearch  │  │
└──────────────────────────┘         │  └────────┘  └──────────────┘  │
                                     └────────────────────────────────┘
```

| 栈 | 部署位置 | 编排文件 | 暴露端口 |
|---|---|---|---|
| 后端栈 | API 服务器 | `./docker-compose.yml` | `${BACKEND_PORT}` (默认 8000) |
| 前端栈 | Web 服务器 | `./frontend/docker-compose.yml` | `${WEB_PORT}` (默认 80) |

两台服务器都需要 Docker Engine 20.10+ 和 Compose V2。

---

## 一、后端部署（API 服务器）

### 1. 上传代码

只需要把以下文件传到 API 服务器：

```
backend/                  # 整个目录
mysql/                    # 整个目录（含 init/）
docker-compose.yml
.env.example
.gitattributes
```

> 也可以整个仓库 `git clone` 到服务器，多余的 frontend/ 不影响。

### 2. 准备数据库 dump

把本地已有的 `quotation` 库导出，放到 `mysql/init/`：

```bash
mysqldump -u root -p --databases quotation \
  --default-character-set=utf8mb4 \
  --single-transaction --routines --triggers \
  > mysql/init/quotation.sql
```

> MySQL 容器**首次启动且 volume 为空**时会自动执行 `mysql/init/*.sql`。后续要重新导入需先 `docker compose down -v`（会清空数据）。

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env
```

必改项：
- `DASHSCOPE_API_KEY` — 百炼 API Key
- `DB_PASSWORD` — MySQL root 密码
- `MEILI_MASTER_KEY` — Meilisearch master key（≥16 字符）
- `JWT_SECRET` — JWT 签名密钥
- `CORS_ORIGINS` — 前端域名白名单，多个用英文逗号分隔，例 `https://web.example.com`

可选：
- `BACKEND_PORT` — 对外端口，默认 8000

### 4. 启动

```bash
docker compose up -d --build
docker compose logs -f backend
```

启动流程：
1. MySQL 启动 → healthcheck 通过 → 首次会自动导入 `mysql/init/*.sql`
2. Meilisearch 启动 → healthcheck 通过
3. Backend `entrypoint.sh` 等两者就绪后启动 uvicorn
4. lifespan 中检测到 Meili 索引为空时**自动同步产品数据**

### 5. 验证

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

如果数据库里没有价格数据，进容器跑一次：

```bash
docker compose exec backend python generate_prices.py
docker compose exec backend python sync_products.py --reset
```

### 6. 安全建议

- **MySQL / Meili 端口**：compose 中已绑定 `127.0.0.1`，对外不可见。如果不需要本机访问，可把 `ports` 整个注释掉。
- **后端建议套一层反代**：在 API 服务器上额外跑一个 nginx，对外只开放 443，做 HTTPS 证书 + 请求限流。
- **防火墙**：只开放 `${BACKEND_PORT}` 给 Web 服务器的 IP。

---

## 二、前端部署（Web 服务器）

### 1. 上传代码

把 `frontend/` 整个目录上传到 Web 服务器即可。

### 2. 配置环境变量

```bash
cd frontend
cp .env.example .env
vim .env
```

```env
BACKEND_URL=http://api.example.com:8000   # 必填，不带尾斜杠
WEB_PORT=80
```

> ⚠️ `BACKEND_URL` 是 **Nginx 容器到后端**的可达地址。
>  - 公网部署：用域名，例 `https://api.example.com`
>  - 内网部署：用内网 IP，例 `http://10.0.0.5:8000`
>  - 不能用 `localhost`，因为是容器内部解析

### 3. 启动

```bash
docker compose up -d --build
docker compose logs -f frontend
```

### 4. 验证

浏览器访问 `http://<web-ip>` 或配的域名，登录测试。

### 5. 切换后端环境

镜像不带后端地址，**改 .env 里的 `BACKEND_URL` 后重启即可**，不用重新构建：

```bash
vim .env
docker compose up -d
```

### 6. HTTPS 建议

生产环境强烈建议在 nginx 容器外面再套一层（Caddy / 宿主 nginx / 阿里云 SLB）做 HTTPS 终止。
或者直接改 `frontend/nginx.conf.template` 加 443 listener，把证书目录挂进容器。

---

## 三、常用运维命令

后端：

```bash
# 状态
docker compose ps

# 看日志
docker compose logs -f backend

# 重启
docker compose restart backend

# 进容器
docker compose exec backend bash
docker compose exec mysql mysql -uroot -p$DB_PASSWORD quotation

# 改了后端代码，重新构建
docker compose build backend && docker compose up -d backend

# 停止
docker compose down

# 停止 + 清空所有数据（⚠️ 危险）
docker compose down -v
```

前端：

```bash
cd frontend
docker compose ps
docker compose logs -f
docker compose build && docker compose up -d   # 改了前端代码
```

---

## 四、常见问题

**Q: 前端访问报 502 / "无法读取响应流"**
- 检查 `BACKEND_URL` 是否能从 Web 服务器访问到（`curl $BACKEND_URL/api/health`）
- 检查后端 `CORS_ORIGINS` 是否包含前端域名
- 检查 API 服务器防火墙是否对 Web 服务器开放 8000

**Q: 流式输出卡顿不流畅**
- nginx 已禁用 buffering，如果你在前面又套了一层 nginx/CDN，确认它也关了 buffering
- 如果走 Cloudflare 等 CDN，需要走"Bypass cache"或 WebSocket/SSE 支持

**Q: 重启后 MySQL 数据没了**
- 别用 `down -v`，那个会删 volume。`down` / `restart` 都安全。

**Q: 改了 mysql/init 里的 SQL，新数据没生效**
- 初始化脚本只在 volume 第一次创建时跑。要么 `down -v` 重来，要么进容器手动 `mysql < /docker-entrypoint-initdb.d/xxx.sql`。

**Q: backend 启动日志显示 `Meilisearch 初始化失败`**
- 索引可能还在异步建中，等十几秒看是否恢复。
- 或者进容器手动同步：`docker compose exec backend python sync_products.py --reset`

**Q: 想用同一个域名的子路径（如 `https://x.com/api`）**
- 把 `BACKEND_URL` 设成空（或本机地址），自己改 `nginx.conf.template` 的 `proxy_pass`。
- 或者把后端 nginx 接到前端 nginx 后面统一转发。
