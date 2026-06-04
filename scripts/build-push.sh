#!/bin/bash
# 本地构建镜像并推送到 Docker Hub
# 用法: bash scripts/build-push.sh
set -e

DOCKER_USER="a3315300155"
BACKEND_IMAGE="${DOCKER_USER}/ai-inquiry-backend:latest"
FRONTEND_IMAGE="${DOCKER_USER}/ai-inquiry-frontend:latest"

echo "=== 构建后端镜像 ==="
docker build -t ${BACKEND_IMAGE} -f backend/Dockerfile backend/

echo "=== 构建前端镜像 ==="
docker build -t ${FRONTEND_IMAGE} -f frontend/Dockerfile frontend/

echo "=== 推送镜像到 Docker Hub ==="
docker push ${BACKEND_IMAGE}
docker push ${FRONTEND_IMAGE}

echo "=== 完成 ==="
