#!/bin/bash

# DailyDigest 部署脚本
# 用法: ./scripts/deploy.sh [dev|prod]

set -e  # 遇到错误立即退出

ENVIRONMENT=${1:-dev}  # 默认为开发环境

echo "🚀 开始部署 DailyDigest ($ENVIRONMENT 环境)..."

# 检查是否在git仓库中
if [ ! -d ".git" ]; then
    echo "❌ 错误：请在项目根目录下运行此脚本"
    exit 1
fi

# 1. 拉取最新代码
echo "📥 拉取最新代码..."
git pull origin main

# 2. 初始化开发环境（如果是开发环境）
if [ "$ENVIRONMENT" = "dev" ]; then
    echo "🔧 初始化开发环境..."
    ./scripts/init-dev-env.sh
fi

# 3. 根据环境选择不同的部署方式
if [ "$ENVIRONMENT" = "dev" ]; then
    echo "🔧 开发环境部署（代码挂载模式）..."
    
    # 停止现有容器
    echo "⏹️  停止现有容器..."
    docker compose -f docker-compose.dev.yml down 2>/dev/null || true
    
    # 检查是否需要重新构建（依赖文件变更）
    NEED_REBUILD=false
    if [ ! "$(docker images -q daily-digest-daily-digest:latest 2>/dev/null)" ]; then
        echo "📦 未找到镜像，需要构建..."
        NEED_REBUILD=true
    elif git diff HEAD~1 HEAD --name-only | grep -q "requirements.txt"; then
        echo "📦 检测到依赖文件变更，需要重新构建..."
        NEED_REBUILD=true
    fi
    
    # 重新构建（如果需要）
    if [ "$NEED_REBUILD" = true ]; then
        echo "🔨 重新构建镜像（包含依赖更新）..."
        docker compose -f docker-compose.dev.yml build --no-cache
    else
        echo "✅ 使用现有镜像，跳过构建..."
    fi
    
    # 启动容器
    echo "▶️  启动容器..."
    docker compose -f docker-compose.dev.yml up -d
    
elif [ "$ENVIRONMENT" = "prod" ]; then
    echo "🏭 生产环境部署（代码内置模式）..."
    
    # 停止现有容器
    echo "⏹️  停止现有容器..."
    docker compose down 2>/dev/null || true
    
    # 强制重新构建镜像
    echo "🔨 重新构建镜像（包含最新代码）..."
    docker compose build --no-cache
    
    # 启动容器
    echo "▶️  启动容器..."
    docker compose up -d
    
else
    echo "❌ 错误：环境参数必须是 'dev' 或 'prod'"
    exit 1
fi

# 4. 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 5. 检查服务状态
echo "🔍 检查服务状态..."
if [ "$ENVIRONMENT" = "dev" ]; then
    docker compose -f docker-compose.dev.yml ps
else
    docker compose ps
fi

# 6. 检查健康状态
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

echo "⚠️  服务可能启动失败，请检查日志："
if [ "$ENVIRONMENT" = "dev" ]; then
    echo "docker compose -f docker-compose.dev.yml logs daily-digest"
else
    echo "docker compose logs daily-digest"
fi 