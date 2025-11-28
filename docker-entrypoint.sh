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

echo "✓ 使用系统 Cron 进行任务调度"

# 启动 Cron Watchdog 监控（后台运行）
echo "Starting Cron Watchdog monitor..."
if [ -f /app/scripts/cron_watchdog.sh ]; then
    nohup /app/scripts/cron_watchdog.sh > /dev/null 2>&1 &
    WATCHDOG_PID=$!
    echo "✓ Cron Watchdog started (PID: $WATCHDOG_PID)"
    echo $WATCHDOG_PID > /var/run/cron_watchdog.pid
    echo "  - 监控间隔: 5分钟"
    echo "  - 日志位置: /app/logs/cron_watchdog.log"
else
    echo "⚠ Warning: cron_watchdog.sh not found, cron monitoring disabled"
fi

echo "=========================================="
echo "Starting FastAPI Application"
echo "=========================================="

# 执行传入的命令
exec "$@"

