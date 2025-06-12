#!/bin/bash

# 依赖更新脚本
# 当 requirements.txt 变更时，重新安装依赖

set -e

echo "📦 更新Python依赖..."

# 检查是否在项目根目录
if [ ! -f "requirements.txt" ]; then
    echo "❌ 错误：未找到 requirements.txt 文件"
    exit 1
fi

# 检查容器是否在运行
if ! docker compose -f docker-compose.dev.yml ps | grep -q "daily-digest"; then
    echo "❌ 错误：开发环境容器未运行，请先启动容器"
    echo "运行: ./scripts/deploy.sh dev"
    exit 1
fi

# 在容器中安装新依赖
echo "🔄 在容器中安装依赖..."
docker compose -f docker-compose.dev.yml exec daily-digest pip install -r requirements.txt

# 重启容器以确保依赖生效
echo "🔄 重启容器..."
docker compose -f docker-compose.dev.yml restart daily-digest

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查健康状态
echo "🏥 检查服务状态..."
for i in {1..5}; do
    if curl -f http://localhost:18899/health >/dev/null 2>&1; then
        echo "✅ 依赖更新完成，服务正常运行！"
        echo "🌐 访问地址: http://localhost:18899"
        exit 0
    fi
    echo "等待服务启动... ($i/5)"
    sleep 2
done

echo "⚠️  服务可能启动失败，请检查日志："
echo "docker compose -f docker-compose.dev.yml logs daily-digest" 