#!/bin/bash
# Cron 服务健康检查脚本
# 用于检测 cron 服务是否正在运行

set -e

# 检查 cron 进程是否存在
check_cron_process() {
    if pgrep -x "cron" > /dev/null; then
        return 0
    else
        return 1
    fi
}

# 检查 cron 服务状态
check_cron_service() {
    if service cron status > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 检查最近是否有任务执行（通过日志）
check_recent_execution() {
    local log_file="/app/logs/cron_crawl_sources.log"
    local max_idle_hours=2

    if [ ! -f "$log_file" ]; then
        echo "警告: 日志文件不存在: $log_file"
        return 0  # 不因为日志文件不存在而失败
    fi

    # 获取日志最后修改时间（秒）
    local last_modified=$(stat -c %Y "$log_file" 2>/dev/null || echo 0)
    local current_time=$(date +%s)
    local idle_seconds=$((current_time - last_modified))
    local idle_hours=$((idle_seconds / 3600))

    if [ $idle_hours -gt $max_idle_hours ]; then
        echo "警告: 爬虫日志超过 ${idle_hours} 小时未更新（最大允许: ${max_idle_hours}小时）"
        return 1
    fi

    return 0
}

# 主检查逻辑
main() {
    local status=0
    local message="Cron 服务健康检查:"

    # 检查进程
    if check_cron_process; then
        message="$message\n✓ Cron 进程运行中"
    else
        message="$message\n✗ Cron 进程未运行"
        status=1
    fi

    # 检查服务状态
    if check_cron_service; then
        message="$message\n✓ Cron 服务状态正常"
    else
        message="$message\n✗ Cron 服务状态异常"
        status=1
    fi

    # 检查最近执行情况（仅警告，不影响退出码）
    if ! check_recent_execution; then
        message="$message\n⚠ 任务可能长时间未执行"
    fi

    # 输出结果
    echo -e "$message"

    return $status
}

# 运行健康检查
main
exit $?
