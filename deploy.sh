#!/bin/bash
# ============================================================
# AI 询价助手 一键部署（本地构建 + 镜像导出 + rsync 传输 + 远程 load）
# 适用于无法访问 Docker Hub 的国内服务器
# 用法: bash deploy.sh
# ============================================================
set -e

echo "========================================"
echo "  AI 询价助手 一键部署（本地构建 + SCP）"
echo "========================================"
echo ""

# ===== 读取部署配置 =====
if [ ! -f ".deploy.env" ]; then
  echo "错误：未找到 .deploy.env 文件！"
  echo "请复制 .deploy.env.example 并填入你的服务器信息："
  echo "  cp .deploy.env.example .deploy.env"
  exit 1
fi

# 去除 Windows 换行符后加载
source <(sed 's/\r$//' .deploy.env)

SERVER_PORT="${SERVER_PORT:-22}"
BACKEND_IMAGE="ai-inquiry-backend:latest"
FRONTEND_IMAGE="ai-inquiry-frontend:latest"
SSH_OPT="-p ${SERVER_PORT}"
RSYNC_SSH="ssh -p ${SERVER_PORT}"

# ===== 构建 =====
echo "[1/5] 构建后端镜像..."
docker build -t "$BACKEND_IMAGE" ./backend || { echo "后端构建失败！"; exit 1; }
echo "      ✓ 后端构建完成"
echo ""

echo "[2/5] 构建前端镜像..."
docker build -t "$FRONTEND_IMAGE" ./frontend || { echo "前端构建失败！"; exit 1; }
echo "      ✓ 前端构建完成"
echo ""

# ===== 导出 =====
echo "[3/5] 导出镜像..."
docker save "$BACKEND_IMAGE" > ai-inquiry-backend.tar
docker save "$FRONTEND_IMAGE" > ai-inquiry-frontend.tar
echo "      ✓ 导出完成"
echo ""

# ===== 传输（rsync 增量 + 压缩传输）=====
echo "[4/5] 增量传输到服务器..."
rsync -az --partial --progress -e "$RSYNC_SSH" \
  ai-inquiry-backend.tar ai-inquiry-frontend.tar \
  "${SERVER_USER}@${SERVER_IP}:${SERVER_DIR}/" || { echo "传输失败！"; exit 1; }
echo "      ✓ 传输完成"
echo ""

# ===== 远程部署（单个 compose 栈：meili + backend + frontend）=====
echo "[5/5] 远程部署..."
ssh ${SSH_OPT} "${SERVER_USER}@${SERVER_IP}" "
  set -e
  cd ${SERVER_DIR}
  git pull
  docker load < ai-inquiry-backend.tar
  docker load < ai-inquiry-frontend.tar
  echo '=== 启动全部服务 ==='
  docker compose up -d
  echo '=== 清理无用镜像 ==='
  docker image prune -f
  echo '部署完成！'
"
echo ""

# ===== 清理本地（服务器上的 .tar 保留，作为下次 rsync 增量比对的基准）=====
rm -f ai-inquiry-backend.tar ai-inquiry-frontend.tar

echo "========================================"
echo "  全部完成！"
echo "========================================"
