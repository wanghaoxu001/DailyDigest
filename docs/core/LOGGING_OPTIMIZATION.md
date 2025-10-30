# 日志管理系统优化

## 概述

本次优化对项目的日志管理进行了全面重构，提供了更强大、更灵活的日志处理能力。

## 主要改进

### 1. 统一日志配置
- **问题**: 之前每个模块都有自己的`logging.basicConfig()`配置，导致重复和冲突
- **解决**: 基于 `logging.config.dictConfig` 的集中式启动流程，`LogManager` 仅负责缓冲与指标管理，实现启动即生效的统一配置

### 2. 分级日志存储
- **文件分离**: 不同类型的日志存储在不同文件中
  - `daily_digest.log`: 主日志文件
  - `errors.log`: 错误日志
  - `crawler.log`: 爬虫专用日志
  - `llm_processor.log`: LLM处理专用日志
  - `daily_digest.json.log`: 结构化JSON日志（可选）

### 3. 多缓冲区内存日志
- **多个缓冲区**: 
  - `general`: 一般日志
  - `crawler`: 爬虫日志
  - `llm`: LLM处理日志
  - `error`: 错误日志
- **结构化条目**: 缓冲区基于 `deque` 维护 `LogEntry`（包含 timestamp/level/logger/context/text）
- **线程安全**: 使用锁机制保证并发安全
- **即时统计**: API 可直接获取级别分布、最新时间戳等指标

### 4. 日志轮转
- **自动轮转**: 日志文件达到最大大小时自动轮转
- **备份保留**: 可配置保留的备份文件数量
- **默认配置**: 10MB文件大小，保留5个备份

### 5. 结构化日志
- **JSON格式**: 支持JSON格式的结构化日志输出
- **上下文信息**: 自动添加模块、函数、行号等上下文信息
- **请求追踪**: 支持请求ID、task_id、source_id 等上下文追踪
- **前端直读**: `/api/logs` 同时返回文本列表与结构化 `entries`，方便前端筛选与高亮

## 配置选项

### 环境变量

```bash
# 日志级别
LOG_LEVEL=INFO

# 日志目录
LOG_DIR=logs

# 启用JSON格式日志
ENABLE_JSON_LOGS=False

# 启用内存缓冲
ENABLE_LOG_BUFFER=True

# 日志文件最大大小（字节）
LOG_MAX_BYTES=10485760

# 备份文件数量
LOG_BACKUP_COUNT=5
```

### 程序配置

```python
from app.config import setup_logging

setup_logging(
    log_level="INFO",           # 日志级别
    log_dir="logs",             # 日志目录
    enable_console=True,         # 控制台输出
    enable_file=True,            # 文件输出
    enable_json=False,           # JSON格式
    enable_buffer=True,          # 内存缓冲环形队列
    max_bytes=10 * 1024 * 1024,  # 最大文件大小
    backup_count=5               # 备份数量
)

```

### Cron 与脚本入口

定时任务脚本（如 `scripts/cron_jobs/crawl_sources_job.py`）在启动时调用 `setup_logging(enable_buffer=False)` 并使用统一命名的 logger（`scripts.cron_jobs.*`）。这样可以确保：

- 文件输出与主站一致（`logs/cron_*.log` 与任务专属文件）
- 日志级别、格式、上下文字段保持统一
- 后续若接入集中式日志系统，可复用相同配置

## API接口

### 获取日志
```http
GET /api/logs/?buffer_name=crawler&max_lines=1000
```

### 清空日志缓冲区
```http
POST /api/logs/clear?buffer_name=crawler
```

### 获取缓冲区列表
```http
GET /api/logs/buffers
```

### 获取日志统计
```http
GET /api/logs/stats
```

### 设置日志级别
```http
POST /api/logs/level
Content-Type: application/json

{
    "level": "DEBUG"
}
```

### 获取当前日志级别
```http
GET /api/logs/level
```

## 使用示例

### 基本日志记录

```python
from app.config import get_logger

logger = get_logger(__name__)

logger.info("这是一条信息日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志", exc_info=True)
```

### 带上下文的日志记录

```python
from app.config import log_with_context, get_logger
import logging

logger = get_logger(__name__)

log_with_context(
    logger, 
    logging.INFO, 
    "用户操作完成",
    user_id=123,
    operation="create_digest",
    duration=2.5
)
```

### 函数调用日志装饰器

```python
from app.config import log_function_call, get_logger

logger = get_logger(__name__)

@log_function_call(logger)
def process_article(article_id):
    # 函数执行会自动记录日志
    pass
```

## 日志格式

### 控制台格式
```
2024-01-15 10:30:45,123 - app.services.crawler - INFO - 开始抓取RSS源
```

### 文件格式
```
2024-01-15 10:30:45,123 - app.services.crawler - INFO - crawler:fetch_rss_feed:123 - 开始抓取RSS源
```

### JSON格式
```json
{
    "timestamp": "2024-01-15T10:30:45.123456",
    "level": "INFO",
    "logger": "app.services.crawler",
    "message": "开始抓取RSS源",
    "module": "crawler",
    "function": "fetch_rss_feed",
    "line": 123,
    "request_id": "N/A"
}
```

## 性能特性

### 1. 内存优化
- 缓冲区自动限制最大行数（默认1000行）
- 超出限制时自动清理旧日志
- 使用StringIO减少内存分配

### 2. 线程安全
- 所有缓冲区操作都使用锁保护
- 支持多线程并发写入

### 3. 异步友好
- 不阻塞主线程
- 文件写入使用缓冲机制

## 迁移指南

### 旧代码
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

### 新代码
```python
from app.config import get_logger

logger = get_logger(__name__)
```

### 获取日志（旧）
```python
from app.services.crawler import get_recent_logs

logs = get_recent_logs()
```

### 获取日志（新）
```python
from app.config import log_manager

logs = log_manager.get_recent_logs('crawler')
```

## 故障排除

### 1. 日志文件权限问题
确保应用有权限写入日志目录：
```bash
chmod 755 logs/
```

### 2. 磁盘空间不足
检查日志轮转配置，适当降低文件大小限制：
```python
setup_logging(max_bytes=5*1024*1024)  # 5MB
```

### 3. 性能影响
如果日志过多影响性能，可以：
- 提高日志级别：`LOG_LEVEL=WARNING`
- 禁用某些缓冲区：`enable_buffer=False`
- 减少备份数量：`backup_count=2`

## 最佳实践

### 1. 日志级别使用
- **DEBUG**: 详细的诊断信息
- **INFO**: 一般操作信息
- **WARNING**: 警告信息
- **ERROR**: 错误信息
- **CRITICAL**: 严重错误

### 2. 日志内容
- 使用清晰的描述性消息
- 包含必要的上下文信息
- 避免记录敏感信息（密码、密钥等）

### 3. 性能考虑
- 避免在循环中大量日志输出
- 使用合适的日志级别
- 考虑异步日志处理

### 4. 监控建议
- 定期检查错误日志
- 监控日志文件大小
- 设置日志告警机制 
