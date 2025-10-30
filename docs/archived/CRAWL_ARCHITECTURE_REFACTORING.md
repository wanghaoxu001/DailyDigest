# 抓取任务架构问题分析与重构方案

## 🔴 当前架构的严重问题

### 1. subprocess.Popen() 的问题

**当前实现** (`app/api/endpoints/sources.py:40-59`):
```python
def _run_background_job(script_name: str, env_overrides: Optional[Dict[str, str]] = None) -> None:
    subprocess.Popen(
        [python_executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_root,
        env=env,
    )
```

**问题清单**:

1. **无法监控进程状态**
   - 进程启动后立即返回
   - 无法知道任务是否真正执行
   - 无法获取执行结果

2. **stdout/stderr 被丢弃**
   - 创建了 PIPE 但从不读取
   - 子进程的所有输出丢失
   - 调试困难

3. **环境变量传递复杂**
   - 需要子进程自己 `load_dotenv()`
   - 环境隔离不彻底
   - 配置管理混乱

4. **资源管理问题**
   - 子进程可能成为孤儿进程
   - 没有超时机制
   - 没有进程清理

5. **日志转发死锁**
   - 子进程尝试 HTTP 回调到主进程
   - 造成潜在的死锁问题
   - 已被迫禁用日志转发

### 2. 系统 Cron 的问题

**当前方式**:
```bash
# 系统 crontab
0 * * * * python /app/scripts/cron_jobs/crawl_sources_job.py
```

**问题**:

1. **独立进程，资源隔离**
   - 与主应用完全独立
   - 不共享数据库连接池
   - 不共享内存缓存

2. **无法利用 FastAPI 的优势**
   - 无法使用依赖注入
   - 无法使用中间件
   - 无法统一错误处理

3. **调试和监控困难**
   - 日志分散
   - 无法通过 API 查询状态
   - 无法实时监控

4. **配置分散**
   - 环境变量需要多处配置
   - 数据库连接需要重新建立
   - 配置不一致风险

---

## ✅ 推荐的架构：BackgroundTasks + APScheduler

### 方案对比

| 特性 | 当前方案 (subprocess) | 推荐方案 (BackgroundTasks) |
|------|----------------------|---------------------------|
| 进程模型 | 独立进程 | 主进程的后台线程/协程 |
| 资源共享 | ❌ 不共享 | ✅ 共享连接池、缓存 |
| 日志 | ❌ 分散 | ✅ 统一 |
| 监控 | ❌ 困难 | ✅ 容易 |
| 调试 | ❌ 困难 | ✅ 容易 |
| 性能 | 🟡 启动开销大 | ✅ 启动快 |
| Cron 集成 | ❌ 系统 crontab | ✅ APScheduler |

### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
│                                                           │
│  ┌────────────────────────────────────────────────────┐ │
│  │              API Endpoints Layer                    │ │
│  │  • POST /api/sources/scheduler/crawl-now          │ │
│  │  • POST /api/sources/{id}/crawl                   │ │
│  │  • GET  /api/sources/scheduler/executions         │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│                    ▼                                      │
│  ┌────────────────────────────────────────────────────┐ │
│  │         BackgroundTasks / Task Queue               │ │
│  │  • 接收任务请求                                     │ │
│  │  • 立即返回任务ID                                   │ │
│  │  • 异步执行任务                                     │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│                    ▼                                      │
│  ┌────────────────────────────────────────────────────┐ │
│  │           APScheduler (定时触发)                    │ │
│  │  • Cron 表达式调度                                  │ │
│  │  • 定时触发 BackgroundTasks                        │ │
│  │  • 内存中管理，无需系统cron                         │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│                    ▼                                      │
│  ┌────────────────────────────────────────────────────┐ │
│  │            Business Logic Services                  │ │
│  │  • CrawlerService                                   │ │
│  │  • LLMProcessorService                             │ │
│  │  • TaskExecutionService                            │ │
│  └─────────────────┬──────────────────────────────────┘ │
│                    │                                      │
│                    ▼                                      │
│  ┌────────────────────────────────────────────────────┐ │
│  │            Shared Resources                         │ │
│  │  • Database Connection Pool                        │ │
│  │  • Cache (Redis/Memory)                            │ │
│  │  • Logger                                           │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ 具体实现方案

### 方案 1: FastAPI BackgroundTasks (简单，适合轻量任务)

**优点**:
- ✅ FastAPI 内置，无需额外依赖
- ✅ 简单易用
- ✅ 与主应用共享资源

**缺点**:
- ⚠️ 没有任务队列
- ⚠️ 没有重试机制
- ⚠️ 没有任务优先级

**实现示例**:

```python
# app/api/endpoints/sources.py

from fastapi import BackgroundTasks

@router.post("/scheduler/crawl-now")
async def trigger_crawl_now(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """立即触发新闻源抓取任务"""

    # 创建任务记录
    execution = TaskExecution.create_task_start(
        db,
        task_type='crawl_sources',
        message='手动触发抓取任务'
    )

    # 添加到后台任务
    background_tasks.add_task(
        execute_crawl_sources_task,
        execution_id=execution.id
    )

    return {
        "status": "started",
        "execution_id": execution.id,
        "detail": "抓取任务已加入队列"
    }

# 实际执行的函数
async def execute_crawl_sources_task(execution_id: int):
    """后台执行抓取任务"""
    from app.services.crawler import crawl_source
    from app.models.source import Source

    db = SessionLocal()
    try:
        # 获取任务记录
        execution = db.query(TaskExecution).filter(
            TaskExecution.id == execution_id
        ).first()

        # 获取活跃源
        sources = db.query(Source).filter(Source.active == True).all()

        total = len(sources)
        success = 0
        failed = 0

        for i, source in enumerate(sources, 1):
            try:
                execution.update_progress(
                    db, i, total, f"正在抓取: {source.name}"
                )

                crawl_source(source.id)
                success += 1

            except Exception as e:
                logger.error(f"抓取源 {source.name} 失败: {e}")
                failed += 1

        # 标记完成
        execution.complete_task(
            db,
            status='success',
            message=f'抓取完成，成功 {success} 个，失败 {failed} 个',
            items_processed=total,
            items_success=success,
            items_failed=failed
        )

    except Exception as e:
        logger.error(f"抓取任务失败: {e}", exc_info=True)
        if execution:
            execution.fail_task(
                db,
                error_message=str(e),
                error_type=type(e).__name__
            )
    finally:
        db.close()
```

### 方案 2: APScheduler + BackgroundTasks (推荐，功能完整)

**优点**:
- ✅ 完整的定时任务功能
- ✅ Cron 表达式支持
- ✅ 任务持久化
- ✅ 错误重试
- ✅ 任务状态查询

**实现示例**:

```python
# app/services/task_scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

scheduler = AsyncIOScheduler()

async def scheduled_crawl_sources():
    """定时抓取任务"""
    from app.services.crawler import crawl_all_sources

    try:
        await crawl_all_sources()
    except Exception as e:
        logger.error(f"定时抓取失败: {e}", exc_info=True)

def init_scheduler():
    """初始化调度器"""

    # 每小时抓取一次
    scheduler.add_job(
        scheduled_crawl_sources,
        CronTrigger(hour='*'),  # 每小时
        id='crawl_sources_hourly',
        replace_existing=True
    )

    # 每2小时生成事件分组
    scheduler.add_job(
        scheduled_event_groups,
        CronTrigger(hour='*/2'),  # 每2小时
        id='event_groups_2hourly',
        replace_existing=True
    )

    # 每天清理缓存
    scheduler.add_job(
        scheduled_cache_cleanup,
        CronTrigger(hour=2, minute=0),  # 每天凌晨2点
        id='cache_cleanup_daily',
        replace_existing=True
    )

    scheduler.start()
    logger.info("任务调度器已启动")

# app/main.py

from app.services.task_scheduler import init_scheduler, scheduler

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    # 初始化数据库
    update_sources_table()
    run_migrations()

    # 初始化调度器
    init_scheduler()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理"""
    scheduler.shutdown()
```

### 方案 3: Celery (重量级，适合复杂场景)

**优点**:
- ✅ 分布式任务队列
- ✅ 高可用
- ✅ 任务优先级
- ✅ 链式任务
- ✅ 成熟的生态

**缺点**:
- ⚠️ 需要额外的消息队列 (Redis/RabbitMQ)
- ⚠️ 配置复杂
- ⚠️ 架构复杂度提升

**适用场景**:
- 大规模部署
- 需要分布式处理
- 任务量巨大

---

## 📊 方案选择建议

### 小型项目 (当前情况)
**推荐: 方案2 (APScheduler + BackgroundTasks)**

**理由**:
1. 无需额外中间件
2. 配置简单
3. 功能足够
4. 易于调试

### 中型项目
**推荐: 方案2 或 方案3**

**升级路径**:
- 先用 APScheduler
- 如果任务量增大，再升级到 Celery

### 大型项目
**推荐: 方案3 (Celery)**

**理由**:
- 需要分布式
- 需要高可用
- 任务复杂度高

---

## 🚀 迁移步骤

### 第1步: 重构 crawler 为 service

```python
# app/services/crawler_service.py

class CrawlerService:
    """爬虫服务，所有抓取逻辑集中管理"""

    def __init__(self, db: Session):
        self.db = db
        self.logger = get_logger(__name__)

    async def crawl_all_sources(self) -> Dict[str, Any]:
        """抓取所有活跃源"""
        sources = self.db.query(Source).filter(Source.active == True).all()

        results = {
            'total': len(sources),
            'success': 0,
            'failed': 0,
            'sources': []
        }

        for source in sources:
            try:
                result = await self.crawl_source(source.id)
                results['success'] += 1
                results['sources'].append({
                    'source_id': source.id,
                    'status': 'success',
                    'result': result
                })
            except Exception as e:
                results['failed'] += 1
                results['sources'].append({
                    'source_id': source.id,
                    'status': 'failed',
                    'error': str(e)
                })

        return results

    async def crawl_source(self, source_id: int) -> Dict[str, Any]:
        """抓取单个源"""
        source = self.db.query(Source).filter(Source.id == source_id).first()
        if not source:
            raise ValueError(f"Source {source_id} not found")

        # 原有的 crawl_source 逻辑
        # ...

        return {
            'new_articles': count,
            'status': 'success'
        }
```

### 第2步: 使用 BackgroundTasks

```python
# app/api/endpoints/sources.py

@router.post("/scheduler/crawl-now")
async def trigger_crawl_now(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """立即触发抓取"""

    # 创建执行记录
    execution = TaskExecution.create_task_start(
        db, 'crawl_sources', message='手动触发'
    )

    # 添加后台任务
    background_tasks.add_task(
        run_crawl_task,
        execution_id=execution.id
    )

    return {
        "execution_id": execution.id,
        "status": "queued"
    }

async def run_crawl_task(execution_id: int):
    """执行抓取任务"""
    db = SessionLocal()
    try:
        crawler = CrawlerService(db)
        result = await crawler.crawl_all_sources()

        # 更新任务状态
        execution = db.query(TaskExecution).get(execution_id)
        execution.complete_task(
            db,
            status='success',
            message=f"完成，成功 {result['success']} 个",
            items_processed=result['total'],
            items_success=result['success'],
            items_failed=result['failed']
        )
    except Exception as e:
        execution = db.query(TaskExecution).get(execution_id)
        if execution:
            execution.fail_task(db, str(e))
    finally:
        db.close()
```

### 第3步: 添加 APScheduler

```python
# app/main.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup():
    # 每小时自动抓取
    scheduler.add_job(
        auto_crawl_sources,
        CronTrigger(hour='*'),
        id='auto_crawl'
    )

    scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

async def auto_crawl_sources():
    """定时触发抓取"""
    db = SessionLocal()
    try:
        execution = TaskExecution.create_task_start(
            db, 'crawl_sources', message='定时触发'
        )

        crawler = CrawlerService(db)
        await crawler.crawl_all_sources()

        execution.complete_task(db, 'success', '定时抓取完成')
    finally:
        db.close()
```

### 第4步: 移除 subprocess 和独立脚本

```bash
# 删除
rm scripts/cron_jobs/crawl_sources_job.py
rm scripts/cron_jobs/event_groups_job.py
rm scripts/cron_jobs/cache_cleanup_job.py

# 移除系统 crontab
crontab -e  # 删除相关行
```

---

## 🎯 改进后的优势

### 1. 统一的资源管理
- ✅ 共享数据库连接池
- ✅ 共享内存缓存
- ✅ 统一的日志系统

### 2. 更好的监控
- ✅ 实时任务状态
- ✅ 统一的错误处理
- ✅ 完整的审计日志

### 3. 更容易调试
- ✅ 所有代码在同一进程
- ✅ 可以使用断点调试
- ✅ 日志集中管理

### 4. 更灵活的配置
- ✅ 通过 API 动态调整 cron
- ✅ 无需重启修改调度
- ✅ 配置统一管理

### 5. 更好的性能
- ✅ 无进程启动开销
- ✅ 复用连接和资源
- ✅ 更高的并发能力

---

## ⚡ 快速开始

**最小改动方案** (保留现有代码，只改触发方式):

```python
# app/api/endpoints/sources.py

@router.post("/scheduler/crawl-now")
async def trigger_crawl_now(
    background_tasks: BackgroundTasks
):
    """立即触发抓取 - 改进版"""

    # 直接在后台执行，不用 subprocess
    background_tasks.add_task(execute_crawl_in_background)

    return {"status": "queued", "detail": "任务已加入队列"}

async def execute_crawl_in_background():
    """后台执行抓取逻辑（直接调用现有代码）"""
    from scripts.cron_jobs.crawl_sources_job import main

    # 在同一进程中执行
    try:
        main()
    except Exception as e:
        logger.error(f"后台抓取失败: {e}", exc_info=True)
```

这样改动最小，但已经解决了 subprocess 的主要问题。

---

## 📝 总结

当前的 `subprocess.Popen()` 方案存在**严重的架构缺陷**：

1. ❌ 进程隔离导致资源浪费
2. ❌ 日志分散难以调试
3. ❌ 无法有效监控
4. ❌ 环境变量管理混乱
5. ❌ 存在死锁风险

**推荐的改进方案**:

- 🥇 **短期**: FastAPI BackgroundTasks (最小改动)
- 🥇 **中期**: APScheduler + BackgroundTasks (推荐)
- 🥈 **长期**: Celery (如果需要分布式)

**关键原则**:
> Cron 只是触发器，业务逻辑应该在主应用中执行

这样可以：
- ✅ 统一管理
- ✅ 共享资源
- ✅ 易于监控
- ✅ 便于调试
