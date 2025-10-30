# Cron定时任务系统测试清单

## 测试环境
- 日期：2025-10-27
- 架构：系统cron + 独立脚本
- 数据库锁：数据库级别并发控制

## 功能测试清单

### ✅ 1. 数据库迁移测试
```bash
cd /root/DailyDigest
python -c "from app.db.update_schema import run_migrations; run_migrations()"
```
- [ ] 检查cron_configs表是否创建成功
- [ ] 检查是否有3条默认配置记录
- [ ] 检查TaskExecution模型是否有acquire_lock和release_lock方法

### ✅ 2. 独立脚本测试
```bash
# 测试新闻源抓取脚本
python /root/DailyDigest/scripts/cron_jobs/crawl_sources_job.py

# 测试事件分组脚本
python /root/DailyDigest/scripts/cron_jobs/event_groups_job.py

# 测试缓存清理脚本
python /root/DailyDigest/scripts/cron_jobs/cache_cleanup_job.py
```
- [ ] 脚本能够正常执行
- [ ] 数据库锁机制工作正常（同时运行两个相同脚本，第二个应该跳过）
- [ ] TaskExecution表中有正确的执行记录
- [ ] 日志文件正常输出

### ✅ 3. Cron配置管理测试
```bash
# 安装crontab
python /root/DailyDigest/scripts/install_crontab.py

# 验证crontab
crontab -l
```
- [ ] crontab正确安装
- [ ] 包含三个任务的cron表达式
- [ ] 日志输出路径正确

### ✅ 4. API端点测试

#### 4.1 查询cron配置
```bash
curl http://localhost:18899/api/sources/scheduler/cron-configs
```
- [ ] 返回3个配置项
- [ ] 包含task_name、cron_expression、enabled等字段

#### 4.2 更新cron配置
```bash
curl -X PUT http://localhost:18899/api/sources/scheduler/cron-configs/1 \
  -H "Content-Type: application/json" \
  -d '{"cron_expression": "0 */2 * * *", "enabled": true}'
```
- [ ] 配置更新成功
- [ ] 数据库中记录已更新

#### 4.3 重新加载crontab
```bash
curl -X POST http://localhost:18899/api/sources/scheduler/cron-reload
```
- [ ] crontab重新加载成功
- [ ] 验证结果正确

#### 4.4 查看调度器状态
```bash
curl http://localhost:18899/api/sources/scheduler/status
```
- [ ] 返回scheduler_type: "cron"
- [ ] cron_verified状态正确
- [ ] 包含running_tasks和recent_executions

#### 4.5 手动触发任务
```bash
# 触发抓取
curl -X POST http://localhost:18899/api/sources/scheduler/crawl-now

# 触发事件分组
curl -X POST http://localhost:18899/api/sources/scheduler/event-groups-now \
  -H "Content-Type: application/json" \
  -d '{"use_multiprocess": true}'

# 触发缓存清理
curl -X POST http://localhost:18899/api/sources/scheduler/cache-cleanup-now
```
- [ ] 任务立即在后台启动
- [ ] 返回status: "started"
- [ ] TaskExecution表中有记录

### ✅ 5. Web界面测试

访问 http://localhost:18899/admin，切换到"定时任务"标签页：

#### 5.1 状态卡片
- [ ] Cron状态显示"Cron已配置"
- [ ] 24h执行次数正确
- [ ] 24h错误次数正确
- [ ] 运行中任务数正确

#### 5.2 Cron配置表格
- [ ] 显示3个任务配置
- [ ] 任务名称正确（新闻源抓取、事件分组、缓存清理）
- [ ] Cron表达式正确显示
- [ ] 启用/禁用状态正确
- [ ] "编辑"按钮可点击

#### 5.3 编辑Cron配置
- [ ] 点击"编辑"按钮打开模态框
- [ ] 表单字段正确填充
- [ ] 修改cron表达式并保存
- [ ] 配置更新成功提示
- [ ] 表格自动刷新显示新值

#### 5.4 重新加载Crontab
- [ ] 点击"重新加载Crontab"按钮
- [ ] 显示加载中状态
- [ ] 成功提示
- [ ] 系统crontab已更新

#### 5.5 手动触发任务
- [ ] "立即抓取新闻源"按钮工作正常
- [ ] "立即计算相似度和分组"按钮工作正常（多进程/单进程选项）
- [ ] "立即执行缓存清理"按钮工作正常
- [ ] 成功提示显示
- [ ] 执行历史表格自动刷新

#### 5.6 执行历史
- [ ] 显示最近的执行记录
- [ ] 任务类型、状态、消息、执行时间正确
- [ ] 可以按任务类型过滤
- [ ] 刷新按钮工作正常

### ✅ 6. Docker容器测试

```bash
# 重新构建镜像
docker-compose build

# 启动容器
docker-compose up -d

# 检查容器日志
docker-compose logs -f
```
- [ ] 容器成功启动
- [ ] cron服务在容器中运行
- [ ] entrypoint脚本正确执行
- [ ] crontab在容器启动时自动安装
- [ ] FastAPI应用正常运行

### ✅ 7. 并发控制测试

同时执行两个相同的任务：
```bash
python /root/DailyDigest/scripts/cron_jobs/crawl_sources_job.py &
python /root/DailyDigest/scripts/cron_jobs/crawl_sources_job.py &
```
- [ ] 第一个任务正常执行
- [ ] 第二个任务检测到锁，立即退出
- [ ] 日志显示"任务已在运行中，跳过"
- [ ] 数据库中只有一条running记录

### ✅ 8. 僵尸任务清理测试

1. 手动在数据库中创建一个超过2小时的running任务
2. 运行任务脚本
- [ ] 脚本检测到僵尸任务
- [ ] 僵尸任务被强制完成
- [ ] 新任务成功获取锁并执行

### ✅ 9. 日志测试

检查日志文件：
```bash
tail -f /root/DailyDigest/logs/cron_crawl_sources.log
tail -f /root/DailyDigest/logs/cron_event_groups.log
tail -f /root/DailyDigest/logs/cron_cache_cleanup.log
tail -f /root/DailyDigest/logs/daily_digest.log
```
- [ ] cron任务日志正确输出
- [ ] 日志格式清晰易读
- [ ] 包含任务ID、开始时间、进度、完成状态
- [ ] 错误日志包含详细堆栈信息

### ✅ 10. 长时间运行测试

让系统运行24小时：
- [ ] cron任务按时执行
- [ ] 没有任务卡死
- [ ] 没有僵尸进程
- [ ] TaskExecution表中记录完整
- [ ] 数据库性能正常

## 性能基准

### 任务执行时间（参考值）
- 新闻源抓取：2-10分钟（取决于源数量和网络）
- 事件分组（多进程）：5-30分钟（取决于新闻数量）
- 缓存清理：< 1分钟

### 资源占用
- CPU：任务执行期间 < 80%
- 内存：< 2GB
- 磁盘：日志轮转正常，不会无限增长

## 回归测试

确保以下功能不受影响：
- [ ] 新闻源管理正常
- [ ] 新闻列表和详情正常
- [ ] 快报生成功能正常
- [ ] PDF导出功能正常
- [ ] 其他系统功能正常

## 已知问题

无

## 测试结论

- [ ] 所有核心功能测试通过
- [ ] 所有API端点测试通过
- [ ] Web界面功能正常
- [ ] Docker容器运行正常
- [ ] 性能符合预期
- [ ] 可以上线生产环境

## 测试者签名

测试者：AI Assistant
测试日期：2025-10-27
版本：Cron Scheduler v1.0

