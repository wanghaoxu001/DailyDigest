#!/bin/bash

# 快速重启脚本（开发环境）
# 使用统一的Docker配置，通过profile控制开发环境

set -e

echo "🔄 快速重启 DailyDigest (开发环境)..."

# 检查是否在项目根目录
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ 错误：请在项目根目录下运行此脚本"
    exit 1
fi

# 检查环境配置文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件，创建开发环境配置..."
    if [ -f "env.example" ]; then
        cp env.example .env
        # 设置开发环境变量
        sed -i 's/BUILD_ENV=production/BUILD_ENV=development/' .env 2>/dev/null || true
        sed -i 's/FLASK_ENV=production/FLASK_ENV=development/' .env 2>/dev/null || true
    else
        echo "BUILD_ENV=development" > .env
        echo "FLASK_ENV=development" >> .env
    fi
    echo "✅ 已创建开发环境配置文件"
fi

# 检查是否存在监听18899端口的进程，如果不存在则启动服务，否则重启服务
DEV_PORT=$(grep "^DEV_PORT=" .env 2>/dev/null | cut -d'=' -f2 || echo "18899")
if ! lsof -i:${DEV_PORT} >/dev/null 2>&1; then
    echo "🔄 启动开发环境服务..."
    docker compose --profile dev up -d daily-digest-dev
else
    echo "🔄 重启开发环境服务..."
    docker compose --profile dev restart daily-digest-dev
fi

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查健康状态
echo "🏥 检查服务状态..."
DEV_PORT=$(grep "^DEV_PORT=" .env 2>/dev/null | cut -d'=' -f2 || echo "18899")
for i in {1..5}; do
    if curl -f http://localhost:${DEV_PORT}/health >/dev/null 2>&1; then
        echo "✅ 开发环境服务重启成功！"
        echo "🌐 访问地址: http://localhost:${DEV_PORT}"
        echo "📝 查看日志: docker compose --profile dev logs -f daily-digest-dev"
        exit 0
    fi
    echo "等待服务启动... ($i/5)"
    sleep 10
done

echo "⚠️  服务可能启动失败，请检查日志："
echo "docker compose --profile dev logs daily-digest-dev"
echo ""
echo "💡 常用命令："
echo "  查看容器状态: docker compose --profile dev ps"
echo "  查看实时日志: docker compose --profile dev logs -f daily-digest-dev"  
echo "  进入容器调试: docker compose --profile dev exec daily-digest-dev bash"
echo "  完全重建: docker compose --profile dev down && docker compose --profile dev up -d --build daily-digest-dev" 