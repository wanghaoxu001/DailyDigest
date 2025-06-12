#!/bin/bash

# 快速重启脚本（开发环境）
# 当使用代码挂载时，只需要重启容器即可

set -e

echo "🔄 快速重启 DailyDigest (开发环境)..."

# 检查是否在项目根目录
if [ ! -f "docker-compose.dev.yml" ]; then
    echo "❌ 错误：请在项目根目录下运行此脚本"
    exit 1
fi

# 重启容器（保持数据）
echo "🔄 重启容器..."
docker compose -f docker-compose.dev.yml restart daily-digest

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查健康状态
echo "🏥 检查服务状态..."
for i in {1..5}; do
    if curl -f http://localhost:18899/health >/dev/null 2>&1; then
        echo "✅ 服务重启成功！"
        echo "🌐 访问地址: http://localhost:18899"
        exit 0
    fi
    echo "等待服务启动... ($i/5)"
    sleep 2
done

echo "⚠️  服务可能启动失败，请检查日志："
echo "docker compose -f docker-compose.dev.yml logs daily-digest" 