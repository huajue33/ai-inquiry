# syntax=docker/dockerfile:1.6

# ===== Stage 1: build =====
FROM node:20-alpine AS builder

WORKDIR /app

RUN npm config set registry https://registry.npmmirror.com

COPY package*.json ./
RUN npm ci || npm install

COPY . .
RUN npm run build

# ===== Stage 2: nginx =====
FROM nginx:1.27-alpine

RUN apk add --no-cache tzdata gettext && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 默认值，docker-compose 中可覆盖
ENV BACKEND_URL=http://backend:8000

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# nginx 1.19+ 镜像内置 envsubst 机制，会把 /etc/nginx/templates/*.template 渲染到 /etc/nginx/conf.d/*
# 我们只让它替换 BACKEND_URL，避免误伤 nginx 自己的 $var
ENV NGINX_ENVSUBST_TEMPLATE_DIR=/etc/nginx/templates
ENV NGINX_ENVSUBST_TEMPLATE_SUFFIX=.template
ENV NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d
ENV NGINX_ENVSUBST_FILTER='^BACKEND_URL$'

EXPOSE 8080
