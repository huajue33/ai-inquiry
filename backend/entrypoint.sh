#!/usr/bin/env bash
set -e

# 等待 MySQL 可连接（最多 ~120s；MySQL 由宿主机/外部提供）
echo "[entrypoint] 等待 MySQL ${DB_HOST}:${DB_PORT} ..."
for i in $(seq 1 60); do
  if python -c "import pymysql,os; pymysql.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']), user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME']).close()" 2>/dev/null; then
    echo "[entrypoint] MySQL 已就绪"
    break
  fi
  echo "  ... 第 $i 次重试"
  sleep 2
done

# 等待 Meilisearch（容器内通过服务名访问）
echo "[entrypoint] 等待 Meilisearch ${MEILI_URL} ..."
for i in $(seq 1 30); do
  if python -c "import urllib.request,os; urllib.request.urlopen(os.environ['MEILI_URL'] + '/health', timeout=2)" 2>/dev/null; then
    echo "[entrypoint] Meilisearch 已就绪"
    break
  fi
  echo "  ... 第 $i 次重试"
  sleep 2
done

# 启动 FastAPI（lifespan 内会按需自动同步索引）
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
