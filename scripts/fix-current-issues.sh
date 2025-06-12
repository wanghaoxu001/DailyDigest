#!/bin/bash

# 修复当前部署问题的脚本

set -e

echo "🔧 修复当前部署问题..."

# 1. 停止所有相关容器
echo "⏹️  停止现有容器..."
docker compose -f docker-compose.dev.yml down 2>/dev/null || true
docker compose down 2>/dev/null || true

# 2. 清理可能有问题的镜像
echo "🧹 清理可能有问题的镜像..."
docker images | grep daily-digest | awk '{print $3}' | xargs docker rmi -f 2>/dev/null || true

# 3. 初始化开发环境
echo "🔧 初始化开发环境..."
./scripts/init-dev-env.sh

# 4. 检查并修复数据库权限
echo "🔐 修复数据库权限..."
if [ -f "daily_digest.db" ]; then
    chmod 666 daily_digest.db
    echo "✅ 数据库权限已修复"
fi

# 5. 重新构建并启动
echo "🔨 重新构建镜像（包含依赖修复）..."
docker compose -f docker-compose.dev.yml build --no-cache

echo "▶️  启动容器..."
docker compose -f docker-compose.dev.yml up -d

# 6. 等待并检查服务
echo "⏳ 等待服务启动..."
sleep 15

echo "🔍 检查容器状态..."
docker compose -f docker-compose.dev.yml ps

echo "📋 查看最新日志..."
docker compose -f docker-compose.dev.yml logs --tail=20 daily-digest

# 7. 检查健康状态
echo "🏥 检查服务健康状态..."
for i in {1..10}; do
    if curl -f http://localhost:18899/health >/dev/null 2>&1; then
        echo "✅ 服务启动成功！"
        echo "🌐 访问地址: http://localhost:18899"
        exit 0
    fi
    echo "等待服务启动... ($i/10)"
    sleep 3
done

echo "⚠️  服务可能仍有问题，请检查详细日志："
echo "docker compose -f docker-compose.dev.yml logs daily-digest" 