#!/bin/bash
set -e

echo "=========================================="
echo "DailyDigest Container Starting"
echo "=========================================="

# 启动cron服务
echo "Starting cron service..."
service cron start

# 检查cron服务状态
if service cron status > /dev/null 2>&1; then
    echo "✓ Cron service started successfully"
else
    echo "⚠ Warning: Cron service may not be running properly"
fi

# 初始化cron配置（从数据库读取并安装到crontab）
echo "Initializing cron configuration..."
if [ -f /app/scripts/install_crontab.py ]; then
    cd /app
    python /app/scripts/install_crontab.py || echo "⚠ Warning: Failed to install crontab"
else
    echo "⚠ Warning: install_crontab.py not found"
fi

echo "=========================================="
echo "Starting FastAPI Application"
echo "=========================================="

# 执行传入的命令
exec "$@"

