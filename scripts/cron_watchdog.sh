#!/bin/bash
# Cron Watchdog 监控脚本
# 定期检查 cron 服务健康状态，必要时自动重启

set -e

# 配置变量
HEALTHCHECK_SCRIPT="/app/scripts/cron_healthcheck.sh"
CHECK_INTERVAL=300  # 检查间隔（秒），默认5分钟
LOG_FILE="/app/logs/cron_watchdog.log"
MAX_LOG_SIZE=10485760  # 最大日志大小 10MB
RESTART_COOLDOWN=60  # 重启后的冷却时间（秒）
MAX_RESTART_PER_HOUR=3  # 每小时最大重启次数

# 重启计数器（使用关联数组记录最近的重启时间）
declare -a RESTART_TIMES=()

# 日志函数
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# 日志轮转
rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        local size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
        if [ $size -gt $MAX_LOG_SIZE ]; then
            log "INFO" "日志文件超过 ${MAX_LOG_SIZE} 字节，开始轮转"
            mv "$LOG_FILE" "${LOG_FILE}.1"
            touch "$LOG_FILE"
        fi
    fi
}

# 检查是否可以重启（防止频繁重启）
can_restart() {
    local current_time=$(date +%s)
    local one_hour_ago=$((current_time - 3600))

    # 清理1小时前的重启记录
    local new_times=()
    for restart_time in "${RESTART_TIMES[@]}"; do
        if [ $restart_time -gt $one_hour_ago ]; then
            new_times+=($restart_time)
        fi
    done
    RESTART_TIMES=("${new_times[@]}")

    # 检查最近1小时的重启次数
    if [ ${#RESTART_TIMES[@]} -ge $MAX_RESTART_PER_HOUR ]; then
        log "ERROR" "达到最大重启次数限制（${MAX_RESTART_PER_HOUR}次/小时），停止重启"
        return 1
    fi

    return 0
}

# 重启 cron 服务
restart_cron() {
    log "WARN" "准备重启 cron 服务"

    if ! can_restart; then
        log "ERROR" "重启频率过高，放弃重启"
        return 1
    fi

    # 尝试优雅停止
    if pgrep -x "cron" > /dev/null; then
        log "INFO" "尝试优雅停止 cron 进程"
        killall cron 2>/dev/null || true
        sleep 2
    fi

    # 强制终止残留进程
    if pgrep -x "cron" > /dev/null; then
        log "WARN" "优雅停止失败，强制终止进程"
        killall -9 cron 2>/dev/null || true
        sleep 1
    fi

    # 启动 cron 服务
    log "INFO" "启动 cron 服务"
    service cron start

    # 等待服务启动
    sleep 2

    # 验证服务是否成功启动
    if service cron status > /dev/null 2>&1; then
        log "INFO" "✓ Cron 服务已成功重启"

        # 重新加载 crontab 配置
        log "INFO" "重新加载 crontab 配置"
        cd /app && python /app/scripts/install_crontab.py >> "$LOG_FILE" 2>&1 || true

        # 记录重启时间
        RESTART_TIMES+=($(date +%s))

        # 冷却时间
        log "INFO" "等待 ${RESTART_COOLDOWN} 秒冷却时间"
        sleep $RESTART_COOLDOWN

        return 0
    else
        log "ERROR" "✗ Cron 服务重启失败"
        return 1
    fi
}

# 执行健康检查
perform_healthcheck() {
    if [ ! -x "$HEALTHCHECK_SCRIPT" ]; then
        log "ERROR" "健康检查脚本不存在或不可执行: $HEALTHCHECK_SCRIPT"
        return 1
    fi

    # 执行健康检查
    if $HEALTHCHECK_SCRIPT >> "$LOG_FILE" 2>&1; then
        log "INFO" "健康检查通过"
        return 0
    else
        log "WARN" "健康检查失败"
        return 1
    fi
}

# 主监控循环
main() {
    log "INFO" "=========================================="
    log "INFO" "Cron Watchdog 启动"
    log "INFO" "检查间隔: ${CHECK_INTERVAL}秒"
    log "INFO" "健康检查脚本: ${HEALTHCHECK_SCRIPT}"
    log "INFO" "=========================================="

    local consecutive_failures=0
    local max_consecutive_failures=2

    while true; do
        rotate_log

        log "INFO" "执行健康检查..."

        if perform_healthcheck; then
            consecutive_failures=0
        else
            consecutive_failures=$((consecutive_failures + 1))
            log "WARN" "连续失败次数: ${consecutive_failures}/${max_consecutive_failures}"

            # 连续失败达到阈值，尝试重启
            if [ $consecutive_failures -ge $max_consecutive_failures ]; then
                log "ERROR" "健康检查连续失败 ${consecutive_failures} 次，触发自动重启"

                if restart_cron; then
                    consecutive_failures=0
                    log "INFO" "服务已恢复，重置失败计数"
                else
                    log "ERROR" "自动重启失败，将在下次检查时重试"
                fi
            fi
        fi

        log "INFO" "等待 ${CHECK_INTERVAL} 秒后进行下次检查..."
        sleep $CHECK_INTERVAL
    done
}

# 信号处理
trap 'log "INFO" "收到终止信号，Watchdog 退出"; exit 0' SIGTERM SIGINT

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

# 启动主循环
main
