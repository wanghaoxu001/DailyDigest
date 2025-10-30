# Cron定时任务系统说明文档

## 概述

系统已从不稳定的 `schedule` 库 + 线程方案迁移到**系统cron + 独立脚本**的架构，提供更稳定、更健壮的定时任务调度。

## 架构特点

### 核心优势

1. **稳定可靠**：使用久经考验的系统cron作为调度器
2. **任务隔离**：每个任务运行在独立进程中，互不影响
3. **数据库锁**：防止任务重复执行，自动清理僵尸任务
4. **灵活配置**：通过数据库动态管理cron表达式
5. **易于监控**：完整的执行记录和状态查询
6. **手动触发**：Web界面可立即执行任务

### 组件说明

#### 1. 数据库模型

- **CronConfig**: 存储cron调度配置（任务名、cron表达式、启用状态等）
- **TaskExecution**: 增强的任务执行记录（包含锁机制）

#### 2. 独立任务脚本 (`scripts/cron_jobs/`)

- `crawl_sources_job.py`: 新闻源抓取任务
- `event_groups_job.py`: 事件分组任务
- `cache_cleanup_job.py`: 缓存清理任务

每个脚本都具备：
- 数据库锁机制（防止重复执行）
- 完整的日志记录
- 进度跟踪
- 异常处理

#### 3. Cron管理服务 (`app/services/cron_manager.py`)

- 从数据库读取配置
- 生成crontab内容
- 安装到系统cron
- 验证crontab正确性

#### 4. API端点 (`app/api/endpoints/sources.py`)

新增端点：
- `GET /api/sources/scheduler/cron-configs` - 获取cron配置
- `PUT /api/sources/scheduler/cron-configs/{id}` - 更新配置
- `POST /api/sources/scheduler/cron-reload` - 重新加载crontab
- `GET /api/sources/scheduler/cron-verify` - 验证crontab

保留端点（已适配新架构）：
- `GET /api/sources/scheduler/status` - 获取调度器状态
- `POST /api/sources/scheduler/crawl-now` - 手动触发抓取
- `POST /api/sources/scheduler/event-groups-now` - 手动触发事件分组
- `POST /api/sources/scheduler/cache-cleanup-now` - 手动触发缓存清理

## 使用指南

### 初始化配置

系统首次启动时会自动创建默认配置：
- 新闻源抓取：每小时执行一次（`0 */1 * * *`）
- 事件分组：每小时第30分钟执行（`30 */1 * * *`）
- 缓存清理：每天凌晨2点执行（`0 2 * * *`）

### 查看当前配置

```bash
# 通过API查看
curl http://localhost:18899/api/sources/scheduler/cron-configs

# 直接查看系统crontab
crontab -l
```

### 修改调度时间

#### 方式1：通过Web界面（推荐）

访问管理页面 `/admin`，在调度器配置部分修改cron表达式。

#### 方式2：通过API

```bash
curl -X PUT http://localhost:18899/api/sources/scheduler/cron-configs/1 \
  -H "Content-Type: application/json" \
  -d '{"cron_expression": "0 */2 * * *"}'  # 改为每2小时

# 修改后重新加载
curl -X POST http://localhost:18899/api/sources/scheduler/cron-reload
```

### 手动运行任务

#### 方式1：通过Web界面
访问 `/admin` 页面，点击相应的"立即执行"按钮。

#### 方式2：通过API
```bash
# 立即执行新闻源抓取
curl -X POST http://localhost:18899/api/sources/scheduler/crawl-now

# 立即执行事件分组
curl -X POST http://localhost:18899/api/sources/scheduler/event-groups-now \
  -H "Content-Type: application/json" \
  -d '{"use_multiprocess": true}'

# 立即执行缓存清理
curl -X POST http://localhost:18899/api/sources/scheduler/cache-cleanup-now
```

#### 方式3：直接运行脚本
```bash
cd /root/DailyDigest
python scripts/cron_jobs/crawl_sources_job.py
python scripts/cron_jobs/event_groups_job.py
python scripts/cron_jobs/cache_cleanup_job.py
```

### 查看执行日志

```bash
# Cron任务日志
tail -f /root/DailyDigest/logs/cron_crawl_sources.log
tail -f /root/DailyDigest/logs/cron_event_groups.log
tail -f /root/DailyDigest/logs/cron_cache_cleanup.log

# 应用日志
tail -f /root/DailyDigest/logs/daily_digest.log
```

### 查看执行历史

通过API查询：
```bash
# 查看最近20条执行记录
curl http://localhost:18899/api/sources/scheduler/history

# 查看特定任务类型的历史
curl http://localhost:18899/api/sources/scheduler/history?task_type=crawl_sources

# 查看执行统计
curl http://localhost:18899/api/sources/scheduler/statistics
```

## 故障排查

### 问题1：任务没有按时执行

**检查步骤：**

1. 确认cron服务运行正常
```bash
service cron status
```

2. 检查crontab是否正确安装
```bash
crontab -l
# 或通过API
curl http://localhost:18899/api/sources/scheduler/cron-verify
```

3. 查看cron日志
```bash
grep CRON /var/log/syslog
```

4. 检查脚本权限
```bash
ls -la /root/DailyDigest/scripts/cron_jobs/
```

**解决方法：**
```bash
# 重新加载crontab
curl -X POST http://localhost:18899/api/sources/scheduler/cron-reload

# 或手动重新安装
cd /root/DailyDigest
python scripts/install_crontab.py
```

### 问题2：任务一直显示"运行中"

这说明上次任务可能异常退出，数据库锁未释放。

**解决方法：**

数据库锁机制会自动检测并清理超过2小时的僵尸任务。如需立即清理：

```python
from app.db.session import SessionLocal
from app.models.task_execution import TaskExecution

db = SessionLocal()
# 查找僵尸任务
zombies = db.query(TaskExecution).filter(
    TaskExecution.status == 'running',
    TaskExecution.updated_at < datetime.now() - timedelta(hours=2)
).all()

# 手动完成
for task in zombies:
    task.status = 'error'
    task.error_message = '手动清理僵尸任务'
    db.commit()
```

### 问题3：容器中cron不工作

**检查步骤：**

1. 确认容器启动时cron服务已启动
```bash
docker exec <container_id> service cron status
```

2. 查看容器日志
```bash
docker logs <container_id>
```

**解决方法：**

确保使用了正确的entrypoint脚本：
```bash
docker-compose down
docker-compose up -d
```

### 问题4：任务执行但无输出

检查日志文件是否有权限问题：
```bash
ls -la /root/DailyDigest/logs/
chmod 755 /root/DailyDigest/logs
```

## Cron表达式说明

格式：`分钟 小时 日 月 星期 命令`

常用示例：
```bash
# 每小时执行
0 */1 * * *

# 每30分钟执行
*/30 * * * *

# 每天凌晨2点执行
0 2 * * *

# 每周一早上9点执行
0 9 * * 1

# 每月1号凌晨3点执行
0 3 1 * *
```

在线工具：https://crontab.guru/

## 测试

运行测试脚本验证所有任务：
```bash
bash /root/DailyDigest/scripts/test_cron_jobs.sh
```

## 迁移说明

从旧的schedule架构迁移到cron架构：

1. 旧的scheduler服务已重命名为 `scheduler.py.old`（保留作为参考）
2. 所有配置数据保留在数据库中
3. TaskExecution表结构兼容，历史记录不受影响
4. API端点保持兼容（除了删除的restart/health-check/settings端点）
5. Web界面需要适配新的API

## 性能优化

1. **避免任务冲突**：通过数据库锁确保同一时刻只有一个任务实例运行
2. **日志管理**：cron任务日志使用追加模式，定期清理旧日志
3. **资源隔离**：每个任务独立进程，OOM不会影响其他任务
4. **可观测性**：完整的执行记录便于性能分析和故障排查

## 总结

新的cron架构比旧的schedule+threading方案更加稳定、可靠、易于维护。所有任务调度由操作系统级别的cron服务保证，不再依赖Python进程的持续运行。

