# 调度器监控和告警机制说明

## 心跳超时告警的三个位置

当调度器心跳超过5分钟未更新时，系统会在以下三个位置记录告警：

### 1. 应用日志 📝

**位置：**
- 容器内：`/app/logs/daily_digest.log`
- 主机查看：`docker compose --profile dev logs daily-digest-dev`

**告警级别：**
- `WARNING`: 检测到调度器不健康
- `ERROR`: 调度器线程已停止，尝试自动重启

**示例日志：**
```
2025-10-25 03:30:00 - app.services.scheduler - WARNING - 检测到调度器不健康: ['心跳超时 (5.2分钟未更新)']
2025-10-25 03:30:00 - app.services.scheduler - ERROR - 调度器线程已停止，尝试自动重启...
2025-10-25 03:30:01 - app.services.scheduler - INFO - 调度器线程已自动重启
```

**查看方法：**
```bash
# 查看实时日志
docker compose --profile dev logs -f daily-digest-dev | grep -E "(WARNING|ERROR)"

# 查看调度器相关日志
docker compose --profile dev logs daily-digest-dev | grep scheduler

# 查看心跳和恢复相关日志
docker compose --profile dev logs daily-digest-dev | grep -E "(心跳|不健康|自动恢复)"
```

---

### 2. 数据库任务执行记录 📊

**位置：**
- 数据库表：`task_executions`
- 任务类型：`task_type = 'scheduler'`

**记录内容：**
- 检测到异常时创建记录
- 记录包含：`health_issues` 详情
- 自动恢复成功/失败的结果

**示例记录：**
```json
{
  "task_type": "scheduler",
  "status": "info",
  "message": "自动恢复：检测到调度器线程停止，正在重启",
  "details": {
    "health_issues": ["心跳超时 (5.2分钟未更新)", "调度器线程未运行"]
  },
  "start_time": "2025-10-25T03:30:00",
  "end_time": "2025-10-25T03:30:01"
}
```

**查询方法：**
```bash
# SQL查询
sqlite3 daily_digest.db "
  SELECT id, task_type, status, message, start_time, details 
  FROM task_executions 
  WHERE task_type = 'scheduler' 
    AND (message LIKE '%不健康%' 
      OR message LIKE '%超时%' 
      OR message LIKE '%恢复%')
  ORDER BY start_time DESC 
  LIMIT 10;
"

# 通过API查询
curl http://localhost:18899/api/sources/scheduler/history
```

---

### 3. 健康检查API 🔍

**接口地址：**
```
GET /api/sources/scheduler/health-check
```

**返回示例（异常时）：**
```json
{
  "is_healthy": false,
  "is_running": true,
  "thread_alive": false,
  "last_heartbeat": "2025-10-25T03:20:00.000000",
  "heartbeat_age_seconds": 600.5,
  "scheduled_jobs_count": 3,
  "health_issues": [
    "调度器线程未运行",
    "心跳超时 (10.0分钟未更新)"
  ],
  "current_time": "2025-10-25T03:30:00.000000",
  "detail": "调度器状态异常",
  "recommendation": "建议使用 POST /api/sources/scheduler/restart 重启调度器"
}
```

**查询方法：**
```bash
# 检查健康状态
curl http://localhost:18899/api/sources/scheduler/health-check

# 查看完整状态
curl http://localhost:18899/api/sources/scheduler/status
```

---

## 自动恢复机制

### 工作原理

1. **后台监控线程**
   - 每2分钟自动检查一次调度器健康状态
   - 检测项：线程存活、心跳年龄、任务列表

2. **自动恢复流程**
   ```
   检测异常 → 记录告警 → 尝试修复 → 记录结果
   ```

3. **恢复策略**
   - **线程停止**：重启调度器线程
   - **任务列表为空**：重新设置定时任务
   - **心跳超时**：上述两项都会检查

### 监控周期

| 检查项 | 周期 | 超时阈值 |
|--------|------|----------|
| 心跳更新 | 每分钟 | 5分钟 |
| 健康检查 | 每2分钟 | - |
| 任务列表检查 | 每小时 | - |

---

## 监控脚本

创建一个监控脚本 `scripts/monitor_scheduler.sh`：

```bash
#!/bin/bash
# 调度器健康监控脚本

API_BASE="http://localhost:18899/api/sources/scheduler"

echo "=== 调度器健康检查 ==="
echo ""

# 1. 检查健康状态
echo "1. 健康状态："
HEALTH=$(curl -s "${API_BASE}/health-check")
IS_HEALTHY=$(echo "$HEALTH" | jq -r '.is_healthy')

if [ "$IS_HEALTHY" = "true" ]; then
    echo "   ✅ 调度器运行正常"
else
    echo "   ❌ 调度器状态异常"
    echo "   问题："
    echo "$HEALTH" | jq -r '.health_issues[]' | sed 's/^/      - /'
    echo ""
    echo "   建议：使用以下命令重启调度器"
    echo "   curl -X POST ${API_BASE}/restart"
fi

echo ""

# 2. 显示心跳信息
echo "2. 心跳状态："
STATUS=$(curl -s "${API_BASE}/status")
HEARTBEAT_AGE=$(echo "$STATUS" | jq -r '.heartbeat_age_seconds')
echo "   最后心跳: ${HEARTBEAT_AGE}秒前"

# 3. 显示下次运行时间
echo ""
echo "3. 下次运行时间："
echo "$STATUS" | jq -r '.next_run_times[]' | sed 's/^/   - /'

echo ""
echo "=== 检查完成 ==="
```

**使用方法：**
```bash
chmod +x scripts/monitor_scheduler.sh
./scripts/monitor_scheduler.sh
```

---

## 告警集成建议

### 1. 定期健康检查（Cron）

```bash
# 添加到crontab，每5分钟检查一次
*/5 * * * * curl -s http://localhost:18899/api/sources/scheduler/health-check | \
  jq -r 'if .is_healthy == false then "ALERT: Scheduler unhealthy - \(.health_issues | join(", "))" else empty end' | \
  logger -t scheduler-monitor
```

### 2. 监控系统集成

如果使用 Prometheus/Grafana 等监控系统，可以：

1. 创建自定义指标导出器
2. 监控 `heartbeat_age_seconds` 指标
3. 当 `heartbeat_age_seconds > 300` 时触发告警

### 3. 邮件/钉钉/企微告警

创建告警脚本 `scripts/alert_on_unhealthy.sh`：

```bash
#!/bin/bash
HEALTH=$(curl -s http://localhost:18899/api/sources/scheduler/health-check)
IS_HEALTHY=$(echo "$HEALTH" | jq -r '.is_healthy')

if [ "$IS_HEALTHY" != "true" ]; then
    ISSUES=$(echo "$HEALTH" | jq -r '.health_issues | join(", ")')
    
    # 发送钉钉告警（示例）
    curl -X POST "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN" \
      -H 'Content-Type: application/json' \
      -d "{
        \"msgtype\": \"text\",
        \"text\": {
          \"content\": \"⚠️ 调度器异常告警\n\n问题：${ISSUES}\n时间：$(date)\n\n请登录系统检查或重启调度器\"
        }
      }"
fi
```

---

## 常见问题

### Q: 如何立即查看是否有告警？

A: 执行以下命令：
```bash
curl http://localhost:18899/api/sources/scheduler/health-check | jq
```

### Q: 告警后系统会自动恢复吗？

A: 会的。自动恢复监控线程每2分钟检查一次，发现异常会自动尝试修复。

### Q: 如果自动恢复失败怎么办？

A: 系统会在日志和数据库中记录失败信息，可以：
1. 通过API手动重启：`curl -X POST http://localhost:18899/api/sources/scheduler/restart`
2. 重启整个应用：`bash scripts/quick-restart.sh`

### Q: 历史告警记录保留多久？

A: 数据库中的任务执行记录会根据配置保留（默认30天），可在 `scheduler_configs` 表中查看 `task_execution_retention_days` 配置。

---

## 相关文档

- [调度器使用说明](SCHEDULER_README.md)
- [任务进度跟踪](TASK_PROGRESS_FEATURE.md)
- [强制关闭恢复](FORCE_SHUTDOWN_RECOVERY.md)

