# 部署指南

## 架构概览

```
┌─────────────────────────┐          ┌─────────────────────────────────┐
│     Web 服务器           │  HTTP    │     API 服务器                   │
│                         │ ───────▶ │                                 │
│  ┌───────────────────┐  │          │  ┌──────────┐  ┌────────────┐  │
│  │ frontend (Nginx)  │  │          │  │ backend  │──│ MySQL 8.0  │  │
│  │ 静态资源 + 反代    │  │          │  │ FastAPI  │  │ (宿主机)   │  │
│  └───────────────────┘  │          │  │          │  └────────────┘  │
│                         │          │  │          │  ┌────────────┐  │
│                         │          │  │          │──│Meilisearch │  │
└─────────────────────────┘          │  └──────────┘  └────────────┘  │
                                     └─────────────────────────────────┘
```

| 栈 | 编排文件 | 暴露端口 |
|---|---|---|
| 后端栈（API 服务器） | `./docker-compose.yml` | 8000（可配置） |
| 前端栈（Web 服务器） | `./frontend/docker-compose.yml` | 80（可配置） |

前后端可以部署在同一台机器，也可以分开部署。

**环境要求**：Docker Engine 20.10+ 、Compose V2、MySQL 8.0+（宿主机或远程）

---

## 一、后端部署

### 1.1 上传文件

将以下内容上传到服务器：

```
backend/              # 后端代码
docker-compose.yml    # 后端编排
.env.example          # 环境变量模板
```

### 1.2 准备 MySQL

后端通过 `host.docker.internal` 连接宿主机的 MySQL。确保：

- MySQL 8.0 已安装并运行
- 已创建 `quotation` 数据库并导入数据
- 允许从 Docker 网络连接（通常是 172.17.0.0/16）

```bash
# 导出本地数据库（如果需要迁移）
mysqldump -u root -p --databases quotation \
  --default-character-set=utf8mb4 \
  --single-transaction --routines --triggers \
  > quotation.sql

# 在目标服务器导入
mysql -u root -p < quotation.sql
```

### 1.3 配置环境变量

```bash
cp .env.example .env
vim .env
```

**必填项**：

| 变量 | 说明 | 示例 |
|------|------|------|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | `sk-xxx` |
| `DB_PASSWORD` | MySQL 密码 | `your-password` |
| `DB_NAME` | 数据库名 | `quotation` |
| `MEILI_MASTER_KEY` | Meilisearch 密钥（≥16字符） | `a-secure-key-123` |
| `JWT_SECRET` | JWT 签名密钥 | `random-string-here` |
| `CORS_ORIGINS` | 前端域名白名单 | `https://your-domain.com` |

**可选项**：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHSCOPE_MODEL` | `qwen3.5-plus` | 主模型 |
| `DASHSCOPE_LITE_MODEL` | `qwen-turbo` | 标题生成用的轻量模型 |
| `DB_HOST` | `host.docker.internal` | MySQL 地址 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `root` | MySQL 用户 |
| `BACKEND_PORT` | `8000` | 后端对外端口 |
| `JWT_EXPIRE_MINUTES` | `1440` | Access Token 有效期（分钟） |

### 1.4 启动

```bash
docker compose up -d --build
```

启动流程：
1. Meilisearch 启动 → healthcheck 通过
2. Backend 等待 MySQL + Meilisearch 就绪
3. 首次启动自动同步产品数据到 Meilisearch

### 1.5 验证

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

### 1.6 数据初始化（首次）

如果 Meilisearch 索引为空（首次启动会自动同步），也可手动执行：

```bash
# 同步产品到搜索引擎
docker compose exec backend python sync_products.py --reset

# 生成模拟价格数据（如果需要）
docker compose exec backend python generate_prices.py
```

### 1.7 执行数据库索引优化

```bash
docker compose exec backend python -c "
import pymysql, os
conn = pymysql.connect(
    host=os.environ['DB_HOST'],
    port=int(os.environ['DB_PORT']),
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    database=os.environ['DB_NAME']
)
with open('migrations/002_performance_indexes.sql') as f:
    sql = f.read()
cursor = conn.cursor()
cursor.execute(sql)
conn.commit()
conn.close()
print('索引创建完成')
"
```

或者直接进 MySQL 执行：

```bash
mysql -u root -p quotation < backend/migrations/002_performance_indexes.sql
```

---

## 二、前端部署

### 2.1 上传文件

将 `frontend/` 目录上传到 Web 服务器。

### 2.2 配置环境变量

```bash
cd frontend
cp .env.example .env
vim .env
```

| 变量 | 说明 | 示例 |
|------|------|------|
| `BACKEND_URL` | 后端 API 地址（Nginx 容器到后端的可达地址） | `http://10.0.0.5:8000` |
| `WEB_PORT` | 前端对外端口 | `80` |

> ⚠️ `BACKEND_URL` 不能用 `localhost`（容器内解析不到宿主机）。同机部署用 `http://host.docker.internal:8000` 或宿主机内网 IP。

### 2.3 启动

```bash
docker compose up -d --build
```

### 2.4 验证

浏览器访问 `http://<服务器IP>` 或配置的域名。

---

## 三、同机部署（简化方案）

如果前后端在同一台机器：

```bash
# 1. 启动后端栈
docker compose up -d --build

# 2. 启动前端栈
cd frontend
echo "BACKEND_URL=http://host.docker.internal:8000" > .env
echo "WEB_PORT=80" >> .env
docker compose up -d --build
```

---

## 四、更新部署

### 更新后端代码

```bash
git pull
docker compose build backend
docker compose up -d backend
```

### 更新前端代码

```bash
cd frontend
git pull
docker compose build
docker compose up -d
```

### 仅修改环境变量

```bash
vim .env
docker compose up -d  # 自动重启受影响的容器
```

---

## 五、运维命令

```bash
# ===== 后端 =====
docker compose ps                          # 查看状态
docker compose logs -f backend             # 查看日志
docker compose restart backend             # 重启
docker compose exec backend bash           # 进入容器

# ===== 前端 =====
cd frontend
docker compose logs -f                     # 查看日志
docker compose restart frontend            # 重启

# ===== 数据库 =====
docker compose exec backend python sync_products.py --reset  # 重建搜索索引

# ===== 停止 =====
docker compose down                        # 停止（保留数据）
docker compose down -v                     # 停止 + 清空 Meilisearch 数据（⚠️ 危险）
```

---

## 六、HTTPS 配置

生产环境建议在前端 Nginx 外层再加一层反代做 HTTPS 终止：

**方案 A**：宿主机 Nginx / Caddy

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 关键配置
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }
}
```

**方案 B**：云厂商 SLB / CDN 做 HTTPS 终止

---

## 七、常见问题

**Q: 前端报 502 / "无法读取响应流"**

- 检查 `BACKEND_URL` 是否从前端容器可达：`docker compose exec frontend wget -qO- $BACKEND_URL/api/health`
- 检查后端 `CORS_ORIGINS` 是否包含前端域名
- 检查防火墙是否放行后端端口

**Q: 流式输出卡顿**

- 确认所有层的 Nginx 都关闭了 buffering（`proxy_buffering off`）
- 如果走 CDN，确认支持 SSE / 关闭缓存

**Q: 搜索无结果但数据库有数据**

- 进容器手动同步：`docker compose exec backend python sync_products.py --reset`
- 等待 10-20 秒让 Meilisearch 完成索引

**Q: 采购员查询提示"无权限"**

- 在管理后台 → 用户管理 → 数据权限中为该用户勾选对应的二级分类
- 确认产品确实属于已授权分类的子分类

**Q: Token 过期后页面白屏**

- 正常情况下 refresh token 会自动续期（7天有效）
- 如果 refresh token 也过期，会自动跳转登录页
- 检查浏览器 localStorage 中是否有 `refresh_token`

**Q: 重启后 Meilisearch 数据丢失**

- 不要用 `docker compose down -v`，`-v` 会删除 volume
- `docker compose down` 和 `docker compose restart` 都是安全的
