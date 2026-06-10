#!/bin/bash
# ============================================================
# 定时任务：生成价格数据 + 同步 Meilisearch
# 用途：宝塔「计划任务 → Shell脚本」或系统 crontab 定时调用
# 以 root 执行；在 backend 容器内跑业务脚本（非交互，适配 cron）
# ============================================================
set -uo pipefail

# ---- 可调参数 ----
CONTAINER="ai-inquiry-backend"     # 后端容器名
KEEP_DAYS=30                       # 价格数据保留天数（最近一个月）
PROJECT_DIR="/www/wwwroot/ai-inquiry"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/cron_$(date +%Y%m%d).log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

log "==================== 定时任务开始 ===================="

# 0) 确认容器在运行
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  log "错误：容器 ${CONTAINER} 未运行，本次任务终止"
  exit 1
fi

# 1) 生成价格数据（自动补到今天，并只保留最近 KEEP_DAYS 天）
log "[1/2] 生成价格数据（保留最近 ${KEEP_DAYS} 天）..."
if docker exec "$CONTAINER" python generate_prices.py --keep-days "$KEEP_DAYS" >>"$LOG_FILE" 2>&1; then
  log "[1/2] 价格数据生成完成"
else
  log "[1/2] 价格数据生成失败（详见日志），终止后续步骤"
  exit 1
fi

# 2) 同步产品数据到 Meilisearch
log "[2/2] 同步 Meilisearch..."
if docker exec "$CONTAINER" python sync_products.py >>"$LOG_FILE" 2>&1; then
  log "[2/2] Meilisearch 同步完成"
else
  log "[2/2] Meilisearch 同步失败（详见日志）"
  exit 1
fi

# 3) 清理 14 天前的日志
find "$LOG_DIR" -name 'cron_*.log' -mtime +14 -delete 2>/dev/null

log "==================== 定时任务结束 ===================="
