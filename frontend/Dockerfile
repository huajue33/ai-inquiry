# ===== Stage 1: build =====
FROM node:20-alpine AS builder

WORKDIR /app

RUN npm config set registry https://registry.npmmirror.com

COPY package*.json ./
RUN npm ci || npm install

COPY . .
RUN npm run build

# ===== Stage 2: nginx（只托管构建产物 + 反代 /api 到后端）=====
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
