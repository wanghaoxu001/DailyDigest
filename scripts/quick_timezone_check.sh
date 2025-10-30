#!/bin/bash

echo "🕐 快速时区检查"
echo "=================="

echo "1. 系统时间: $(date)"
echo "2. 时区设置: $(cat /etc/timezone 2>/dev/null || echo '未设置')"
echo "3. TZ环境变量: ${TZ:-未设置}"
echo "4. UTC时间: $(date -u)"

# 计算时差
local_time=$(date +%H)
utc_time=$(date -u +%H)
offset=$((local_time - utc_time))

# 处理跨日期的情况
if [ $offset -lt -12 ]; then
    offset=$((offset + 24))
elif [ $offset -gt 12 ]; then
    offset=$((offset - 24))
fi

echo "5. UTC偏移: +${offset}小时"

if [ $offset -eq 8 ]; then
    echo "✅ 北京时间配置正确！"
    exit 0
else
    echo "❌ 时区配置不正确，预期+8小时"
    exit 1
fi
