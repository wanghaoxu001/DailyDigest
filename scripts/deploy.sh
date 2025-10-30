#!/bin/bash

# DailyDigest 部署脚本 - 统一配置版本
# 用法: ./scripts/deploy.sh [dev|prod]

set -e  # 遇到错误立即退出

ENVIRONMENT=${1:-dev}  # 默认为开发环境

echo "🚀 开始部署 DailyDigest ($ENVIRONMENT 环境) - 统一配置版本..."

# 检查是否在git仓库中
if [ ! -d ".git" ]; then
    echo "❌ 错误：请在项目根目录下运行此脚本"
    exit 1
fi

# 1. 拉取最新代码
echo "📥 拉取最新代码..."
git pull origin main

# 2. 检查环境配置文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到.env文件，创建默认配置..."
    if [ -f "env.example" ]; then
        cp env.example .env
        echo "✅ 已从env.example创建.env文件"
    else
        echo "BUILD_ENV=$ENVIRONMENT" > .env
        echo "FLASK_ENV=$ENVIRONMENT" >> .env
        echo "✅ 已创建基础.env文件"
    fi
fi

# 3. 更新环境变量
echo "🔧 配置环境变量..."
if [ "$ENVIRONMENT" = "dev" ]; then
    sed -i.bak 's/BUILD_ENV=.*/BUILD_ENV=development/' .env 2>/dev/null || true
    sed -i.bak 's/FLASK_ENV=.*/FLASK_ENV=development/' .env 2>/dev/null || true
    echo "✅ 已设置为开发环境"
else
    sed -i.bak 's/BUILD_ENV=.*/BUILD_ENV=production/' .env 2>/dev/null || true
    sed -i.bak 's/FLASK_ENV=.*/FLASK_ENV=production/' .env 2>/dev/null || true
    echo "✅ 已设置为生产环境"
fi

# 4. 根据环境选择不同的部署方式
if [ "$ENVIRONMENT" = "dev" ]; then
    echo "🔧 开发环境部署（代码挂载模式）..."
    
    # 停止现有容器
    echo "⏹️  停止现有容器..."
    docker compose --profile dev down 2>/dev/null || true
    
    # 检查是否需要重新构建（依赖文件变更）
    NEED_REBUILD=false
    if [ ! "$(docker images -q dailydigest-daily-digest-dev:latest 2>/dev/null)" ]; then
        echo "📦 未找到开发环境镜像，需要构建..."
        NEED_REBUILD=true
    elif git diff HEAD~1 HEAD --name-only 2>/dev/null | grep -q "requirements.txt"; then
        echo "📦 检测到依赖文件变更，需要重新构建..."
        NEED_REBUILD=true
    fi
    
    # 重新构建（如果需要）
    if [ "$NEED_REBUILD" = true ]; then
        echo "🔨 重新构建开发环境镜像（包含依赖更新）..."
        docker compose --profile dev build --no-cache daily-digest-dev
    else
        echo "✅ 使用现有镜像，跳过构建..."
    fi
    
    # 启动容器
    echo "▶️  启动开发环境容器..."
    docker compose --profile dev up -d daily-digest-dev
    
elif [ "$ENVIRONMENT" = "prod" ]; then
    echo "🏭 生产环境部署（代码内置模式）..."
    
    # 停止现有容器
    echo "⏹️  停止现有容器..."
    docker compose down 2>/dev/null || true
    
    # 强制重新构建镜像
    echo "🔨 重新构建生产环境镜像（包含最新代码）..."
    docker compose build --no-cache daily-digest
    
    # 启动容器
    echo "▶️  启动生产环境容器..."
    docker compose up -d daily-digest
    
else
    echo "❌ 错误：环境参数必须是 'dev' 或 'prod'"
    echo "用法: ./scripts/deploy.sh [dev|prod]"
    exit 1
fi

# 5. 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 6. 检查服务状态
echo "🔍 检查服务状态..."
if [ "$ENVIRONMENT" = "dev" ]; then
    docker compose --profile dev ps
else
    docker compose ps
fi

# 7. 检查健康状态
echo "🏥 检查服务健康状态..."
for i in {1..10}; do
    if curl -f http://localhost:18899/health >/dev/null 2>&1; then
        echo "✅ 服务启动成功！"
        echo "🌐 访问地址: http://localhost:18899"
        
        # 显示有用的命令
        echo ""
        echo "📝 常用命令："
        if [ "$ENVIRONMENT" = "dev" ]; then
            echo "  查看日志: docker compose --profile dev logs -f daily-digest-dev"
            echo "  进入容器: docker compose --profile dev exec daily-digest-dev bash"
            echo "  快速重启: ./scripts/quick-restart.sh"
            echo "  停止服务: docker compose --profile dev down"
        else
            echo "  查看日志: docker compose logs -f daily-digest"
            echo "  进入容器: docker compose exec daily-digest bash"
            echo "  停止服务: docker compose down"
        fi
        
        exit 0
    fi
    echo "等待服务启动... ($i/10)"
    sleep 3
done

echo "⚠️  服务可能启动失败，请检查日志："
if [ "$ENVIRONMENT" = "dev" ]; then
    echo "docker compose --profile dev logs daily-digest-dev"
else
    echo "docker compose logs daily-digest"
fi

echo ""
echo "🔧 故障排查建议："
echo "1. 检查环境配置: cat .env"
echo "2. 检查端口占用: lsof -i:18899"
echo "3. 检查Docker状态: docker compose ps"
echo "4. 重新构建: BUILD_ENV=$ENVIRONMENT docker compose build --no-cache"