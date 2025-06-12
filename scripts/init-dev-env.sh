#!/bin/bash

# 开发环境初始化脚本
# 确保必要的文件和目录存在，避免挂载问题

set -e

echo "🔧 初始化开发环境..."

# 检查是否在项目根目录
if [ ! -f "docker-compose.dev.yml" ]; then
    echo "❌ 错误：请在项目根目录下运行此脚本"
    exit 1
fi

# 1. 确保数据目录存在
echo "📁 检查并创建数据目录..."
mkdir -p data/logs
mkdir -p data/outputs
mkdir -p data/wechat_articles
mkdir -p data/processed_articles

# 2. 确保数据库文件存在
if [ ! -f "daily_digest.db" ]; then
    echo "🗄️  创建数据库文件..."
    touch daily_digest.db
    # 设置合适的权限
    chmod 666 daily_digest.db
else
    echo "✅ 数据库文件已存在"
    # 确保权限正确
    chmod 666 daily_digest.db
fi

# 3. 确保环境配置文件存在
if [ ! -f ".env" ]; then
    if [ -f "envtemplate.txt" ]; then
        echo "📝 从模板创建 .env 文件..."
        cp envtemplate.txt .env
        echo "⚠️  请编辑 .env 文件配置必要的环境变量"
    else
        echo "⚠️  警告：未找到 .env 文件和模板文件"
    fi
else
    echo "✅ 环境配置文件已存在"
fi

# 4. 检查 requirements.txt
if [ ! -f "requirements.txt" ]; then
    echo "❌ 错误：未找到 requirements.txt 文件"
    exit 1
else
    echo "✅ 依赖文件检查通过"
fi

# 5. 设置目录权限（确保容器可以访问）
echo "🔐 设置目录权限..."
chmod -R 755 data/
chmod 666 daily_digest.db 2>/dev/null || true

echo "✅ 开发环境初始化完成！"
echo "💡 现在可以运行: ./scripts/deploy.sh dev" 