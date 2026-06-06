# 部署指南

## 架构概览

```
用户 → 宝塔 Nginx (:80) ──── SSL 终止 + 反代
  ├── /     → 127.0.0.1:8080  → quotation-frontend (容器内 Nginx + Vue)
  └── /api/ → 127.0.0.1:8000  → quotation-backend (FastAPI)
                                   ├── Meilisearch (容器)
                                   └── MySQL 8.0 (宿主机)
```

| 栈 | 编排文件 | 镜像 | 端口 |
|---|---|---|---|
| 后端栈 | `./docker-compose.yml` | `a3315300155/ai-inquiry-backend:latest` | 8000 |
| 前端栈 | `./frontend/docker-compose.yml` | `a3315300155/ai-inquiry-frontend:latest` | 8080 |

**环境要求**：Docker Engine 20.10+、Compose V2、MySQL 8.0+

---

## 一、部署流程概述

```
本地开发机                         Docker Hub                    服务器
─────────                         ──────────                    ──────

改后端代码
  │
  ▼
bash scripts/build-push.sh  ──▶  upload image  ──▶  等待被拉取
  │
  ▼
git push  ───────────▶  GitHub Actions  ──▶  SSH 到服务器
                                               │
                                        git pull (更新配置)
                                        docker compose pull
                                        docker compose up -d
```

- **构建在本地**：避免服务器 2 核 2G 编译压力
- **镜像托管 Docker Hub**：免费、全球可达
- **部署通过 GitHub Actions**：push 即部署

---

## 二、准备工作

### 2.1 Docker Hub 账号

1. 注册 [Docker Hub](https://hub.docker.com) 账号
2. 创建 Access Token：Settings → Security → Access Tokens → Read & Write
3. 本地登录：`docker login -u <用户名>`，密码填 Token

### 2.2 服务器初始化

```bash
# 克隆仓库
git clone https://github.com/huajue33/ai-inquiry.git /www/wwwroot/ai-inquiry

# 配置后端环境变量（包含数据库密码等敏感信息）
cp /www/wwwroot/ai-inquiry/.env.example /www/wwwroot/ai-inquiry/.env
vim /www/wwwroot/ai-inquiry/.env

# 配置前端环境变量
vim /www/wwwroot/ai-inquiry/frontend/.env

# 登录 Docker Hub（拉取镜像用）
docker login -u <用户名>
```

### 2.3 环境变量

**后端 `.env` 必填项**：

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key |
| `DB_PASSWORD` | MySQL 密码 |
| `DB_NAME` | 数据库名 |
| `MEILI_MASTER_KEY` | Meilisearch 密钥（≥16 字符） |
| `JWT_SECRET` | JWT 签名密钥 |

**前端 `.env`**：

| 变量 | 说明 | 示例 |
|---|---|---|
| `BACKEND_URL` | 后端 API 地址（须带 http://） | `http://127.0.0.1:8000` |
| `WEB_PORT` | 前端容器对外端口 | `8080` |

---

## 三、首次部署

### 3.1 本地构建并推送镜像

```bash
docker login -u <用户名>
bash scripts/build-push.sh
```

### 3.2 服务器启动

```bash
cd /www/wwwroot/ai-inquiry

# 启动后端栈
docker compose pull
docker compose up -d

# 启动前端栈
cd frontend
docker compose pull
docker compose up -d
cd ..

# 清理旧镜像
docker image prune -f
```

### 3.3 配置宝塔 Nginx

宝塔 → 网站 → 域名设置 → 配置文件：

```nginx
server {
    listen 80;
    server_name ai-inquiry.huahuaresume.online;

    client_max_body_size 20m;

    # 反代到前端容器
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket：实时语音识别（必须放在 /api/ 之前，且 Connection 用 upgrade）
    location /api/chat/asr-stream {
        proxy_pass http://127.0.0.1:8000/api/chat/asr-stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }

    # 反代到后端容器（SSE）
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection "";
        chunked_transfer_encoding off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        send_timeout 600s;
    }

    access_log /www/wwwlogs/ai-inquiry.huahuaresume.online.log;
    error_log  /www/wwwlogs/ai-inquiry.huahuaresume.online.error.log;
}
```

### 3.4 验证

```bash
# 后端
curl http://127.0.0.1:8000/api/health
# {"status":"ok"}

# 前端
curl http://127.0.0.1:8080
# 返回 HTML

# 通过域名
curl http://ai-inquiry.huahuaresume.online
```

---

## 四、日常更新

### 更新后端代码

```bash
# 本地
bash scripts/build-push.sh
git add . && git commit -m "描述改动" && git push

# 等待 GitHub Actions 自动部署，或手动到服务器执行：
cd /www/wwwroot/ai-inquiry
git pull
docker compose pull && docker compose up -d
docker image prune -f
```

### 更新前端代码

同后端流程，`build-push.sh` 会同时构建前后端镜像。

### 仅改配置文件

```bash
# 本地改完后直接 push，无需重新构建镜像
git add . && git commit -m "更新配置" && git push
```

### 仅改环境变量

直接在服务器上修改 `.env`，然后重启：

```bash
vim /www/wwwroot/ai-inquiry/.env
docker compose up -d
```

---

## 五、CI/CD（GitHub Actions）

配置文件：`.github/workflows/deploy.yml`

触发条件：`git push` 到 `main` 分支

需要配置的 GitHub Secrets：

| Secret | 说明 |
|---|---|
| `SSH_HOST` | 服务器 IP |
| `SSH_USER` | SSH 用户名 |
| `SSH_PASSWORD` | SSH 密码 |
| `SSH_PORT` | SSH 端口 |

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
cd frontend && docker compose logs -f   # 前端

# 重启服务
docker compose restart backend
cd frontend && docker compose restart

# 重建搜索索引
docker compose exec backend python sync_products.py --reset

# 停止服务
docker compose down                      # 后端（保留数据）
cd frontend && docker compose down       # 前端

# 停止并清空 Meilisearch 数据（危险）
docker compose down -v
```

---

## 七、常见问题

**Q: 前端容器启动失败，日志显示 `invalid URL prefix`**

`BACKEND_URL` 缺少 `http://` 前缀。Nginx `proxy_pass` 需要完整 URL。

**Q: 前端报 502**

- 检查后端是否运行：`docker ps | grep backend`
- 从前端容器内测试：`docker compose exec frontend wget -qO- $BACKEND_URL/api/health`

**Q: pip install 很慢**

本地构建时修改 `backend/Dockerfile` 中的 pip 镜像源为清华镜像：
```
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```
服务器不参与编译，无需担心。

**Q: Docker 基础镜像拉取失败**

Docker Desktop → Settings → Docker Engine 添加国内镜像加速器：
```json
{
  "registry-mirrors": ["https://docker.1ms.run", "https://docker.xuanyuan.me"]
}
```

**Q: 端口冲突**

- 80 端口被宝塔 Nginx 占用 → 前端改用 8080
- 宝塔网站设为「纯静态」，关闭 PHP 以释放内存

**Q: 采购员查询提示"无权限"**

管理后台 → 用户管理 → 数据权限 → 勾选对应的二级分类。

**Q: Meilisearch 数据丢失**

不要使用 `docker compose down -v`（`-v` 会删除 volume）。普通 `down`/`restart` 是安全的。

**Q: Token 过期白屏**

- Refresh token 会自动续期（7 天有效）
- 过期后自动跳转登录页
- 检查浏览器 localStorage 中的 `refresh_token`
