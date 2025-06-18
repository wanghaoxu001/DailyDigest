#!/bin/bash

# 更新相似度计算依赖脚本
# 用于安装BGE模型依赖并重新构建容器

set -e

echo "🔧 更新相似度计算依赖..."

# 检查是否在项目根目录
if [ ! -f "docker-compose.dev.yml" ]; then
    echo "❌ 错误：请在项目根目录下运行此脚本"
    exit 1
fi

echo "📦 停止当前容器..."
docker compose -f docker-compose.dev.yml down

echo "🏗️ 重新构建镜像（包含新的依赖）..."
docker compose -f docker-compose.dev.yml build --no-cache daily-digest

echo "🚀 启动更新后的容器..."
docker compose -f docker-compose.dev.yml up -d

echo "⏳ 等待容器启动..."
sleep 10

echo "📋 检查容器状态..."
docker compose -f docker-compose.dev.yml ps

echo "📊 查看启动日志..."
docker compose -f docker-compose.dev.yml logs --tail=20 daily-digest

echo "✅ 更新完成！"
echo "💡 现在BGE模型应该可以正常加载，相似度计算性能将显著提升"
echo "💡 可以通过以下命令查看实时日志："
echo "   docker compose -f docker-compose.dev.yml logs -f daily-digest" 