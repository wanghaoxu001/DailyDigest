# 定时任务系统使用说明

## 概述

每日安全快报系统现已集成了完整的定时任务功能，可以自动抓取新闻源、处理内容并生成事件分组缓存。

## 功能特性

### 1. 自动新闻源抓取
- **功能**：定时检查所有活跃的新闻源，根据每个源的抓取间隔设置自动抓取最新内容
- **默认间隔**：每1小时检查一次
- **智能跳过**：如果某个源尚未到达其配置的抓取间隔时间，会自动跳过
- **自动处理**：新抓取的文章会自动进行LLM处理（分类、摘要生成、实体提取等）

### 2. 事件分组缓存生成
- **功能**：预生成常用的事件分组查询结果，提高前端响应速度
- **默认间隔**：每1小时生成一次
- **缓存策略**：生成24小时、48小时等不同时间范围的分组

### 3. 缓存清理
- **功能**：自动清理过期的缓存数据
- **执行时间**：每天凌晨2点
- **清理范围**：删除3天前的事件分组缓存

## 使用方法

### 启动系统
定时任务在应用启动时自动启动，无需额外配置。

```bash
python run.py
```

### 状态检查
使用提供的状态检查脚本：

```bash
# 检查系统状态
python check_scheduler_status.py

# 检查状态并立即触发抓取
python check_scheduler_status.py crawl

# 显示帮助信息
python check_scheduler_status.py help
```

### API接口

#### 获取调度器状态
```bash
GET /api/sources/scheduler/status
```

响应示例：
```json
{
    "is_running": true,
    "event_generation_interval": 1,
    "crawl_sources_interval": 1,
    "scheduled_jobs_count": 3,
    "next_run_times": [
        "2025-06-10T17:08:28.696239",
        "2025-06-10T17:08:28.696253",
        "2025-06-11T02:00:00"
    ]
}
```

#### 立即触发新闻源抓取
```bash
POST /api/sources/scheduler/crawl-now
```

#### 更新抓取间隔设置
```bash
PUT /api/sources/scheduler/settings
Content-Type: application/json

{
    "crawl_sources_interval": 2.0
}
```

### 配置调整

#### 修改抓取间隔
可以通过API动态调整新闻源抓取的检查间隔：

```python
import requests

# 设置为每2小时检查一次
response = requests.put(
    "http://localhost:18899/api/sources/scheduler/settings",
    json={"crawl_sources_interval": 2.0}
)
```

#### 单个源的抓取间隔
每个新闻源都有独立的 `fetch_interval` 设置（以秒为单位），可以通过管理界面或API修改：

- 默认值：3600秒（1小时）
- 最小值：1秒（实际建议不低于300秒以避免过于频繁的请求）
- 常用设置：
  - 高频源：1800秒（30分钟）
  - 普通源：3600秒（1小时）
  - 低频源：7200秒（2小时）

## 日志监控

### 查看定时任务日志
```bash
# 查看所有定时任务相关日志
grep -E "(定时|schedule|scheduler)" logs/daily_digest.log | tail -20

# 查看新闻源抓取日志
grep "抓取" logs/crawler.log | tail -20

# 实时监控日志
tail -f logs/daily_digest.log | grep -E "(定时|抓取|schedule)"
```

### 日志文件位置
- 主日志：`logs/daily_digest.log`
- 爬虫日志：`logs/crawler.log`
- 错误日志：`logs/errors.log`

## 故障排除

### 1. 定时任务未运行
**现象**：调度器状态显示 `is_running: false`

**解决方法**：
```bash
# 重启应用
pkill -f "python run.py"
python run.py
```

### 2. 新闻源抓取失败
**现象**：源状态显示错误或长时间未更新

**排查步骤**：
1. 检查网络连接
2. 检查源的URL是否可访问
3. 查看错误日志
4. 手动触发单个源的抓取测试

```bash
# 手动触发特定源的抓取
curl -X POST "http://localhost:18899/api/sources/1/crawl"
```

### 3. 抓取间隔设置异常
**现象**：抓取频率过高或过低

**解决方法**：
1. 检查全局抓取检查间隔设置
2. 检查各个源的 `fetch_interval` 配置
3. 通过API调整设置

## 性能优化建议

### 1. 合理设置抓取间隔
- 根据新闻源的更新频率设置合适的抓取间隔
- 避免设置过短的间隔导致资源浪费
- 对于微信公众号等特殊源，可以设置较长的间隔

### 2. 监控资源使用
- 定期检查CPU和内存使用情况
- 监控数据库大小和性能
- 注意OpenAI API的token消耗

### 3. 错误处理
- 系统具备自动重试机制
- 失败的抓取不会影响其他源的正常运行
- 定期检查和处理异常源

## 系统架构

```
应用启动
    ↓
启动定时任务服务 (SchedulerService)
    ↓
设置三个定时任务：
    ├── 新闻源抓取检查 (每1小时)
    ├── 事件分组生成 (每1小时)
    └── 缓存清理 (每天凌晨2点)
    ↓
后台线程持续运行调度器
    ↓
任务执行：
    ├── 检查所有活跃源的抓取时间
    ├── 抓取新内容并进行LLM处理
    └── 更新源状态和统计信息
```

## 更新历史

- **2025-06-10**: 添加完整的定时新闻源抓取功能
- **2025-06-10**: 添加调度器状态监控API
- **2025-06-10**: 添加状态检查脚本
- **2025-06-10**: 完善日志记录和错误处理

---

如有问题或需要进一步的功能定制，请查看相关日志文件或联系系统管理员。 