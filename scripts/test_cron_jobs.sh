#!/bin/bash
# 测试各个cron任务脚本是否能正常运行

echo "=========================================="
echo "测试Cron任务脚本"
echo "=========================================="
echo

cd /root/DailyDigest

# 测试新闻源抓取脚本
echo "1. 测试新闻源抓取脚本..."
echo "----------------------------------------"
python scripts/cron_jobs/crawl_sources_job.py
if [ $? -eq 0 ]; then
    echo "✓ 新闻源抓取脚本测试通过"
else
    echo "✗ 新闻源抓取脚本测试失败"
fi
echo

# 测试事件分组脚本
echo "2. 测试事件分组脚本..."
echo "----------------------------------------"
python scripts/cron_jobs/event_groups_job.py
if [ $? -eq 0 ]; then
    echo "✓ 事件分组脚本测试通过"
else
    echo "✗ 事件分组脚本测试失败"
fi
echo

# 测试缓存清理脚本
echo "3. 测试缓存清理脚本..."
echo "----------------------------------------"
python scripts/cron_jobs/cache_cleanup_job.py
if [ $? -eq 0 ]; then
    echo "✓ 缓存清理脚本测试通过"
else
    echo "✗ 缓存清理脚本测试失败"
fi
echo

echo "=========================================="
echo "所有测试完成"
echo "=========================================="

