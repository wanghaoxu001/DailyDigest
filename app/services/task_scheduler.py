"""
任务调度服务 - 使用 APScheduler + BackgroundTasks
替代原有的 subprocess + 系统cron 架构
"""
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from app.config import get_logger
from app.db.session import SessionLocal, SQLALCHEMY_DATABASE_URL

logger = get_logger(__name__)

# 全局调度器实例
_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        raise RuntimeError("调度器未初始化，请先调用 init_scheduler()")
    return _scheduler


def init_scheduler() -> BackgroundScheduler:
    """
    初始化APScheduler调度器

    配置说明:
    - BackgroundScheduler: 在后台线程运行，适合FastAPI集成
    - SQLAlchemyJobStore: 持久化任务到数据库，重启后恢复
    - ThreadPoolExecutor: 线程池执行器，max_workers=5
    """
    global _scheduler

    if _scheduler is not None:
        logger.warning("调度器已经初始化，返回现有实例")
        return _scheduler

    # 配置任务存储（持久化到数据库）
    jobstores = {
        'default': SQLAlchemyJobStore(url=SQLALCHEMY_DATABASE_URL)
    }

    # 配置执行器
    executors = {
        'default': ThreadPoolExecutor(max_workers=5)
    }

    # 任务默认配置
    job_defaults = {
        'coalesce': True,  # 合并错过的执行
        'max_instances': 1,  # 同一任务最多1个实例运行
        'misfire_grace_time': 300  # 错过执行的容忍时间（秒）
    }

    _scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone='Asia/Shanghai'  # 统一时区
    )

    logger.info("APScheduler 调度器已初始化")
    return _scheduler


def start_scheduler():
    """启动调度器"""
    global _scheduler

    if _scheduler is None:
        raise RuntimeError("调度器未初始化，请先调用 init_scheduler()")

    if _scheduler.running:
        logger.warning("调度器已在运行中")
        return

    _scheduler.start()
    logger.info("APScheduler 调度器已启动")

    # 加载数据库中的定时任务配置
    load_scheduled_tasks_from_db()


def shutdown_scheduler(wait: bool = True):
    """关闭调度器"""
    global _scheduler

    if _scheduler is None:
        logger.warning("调度器未初始化")
        return

    if not _scheduler.running:
        logger.warning("调度器未运行")
        return

    _scheduler.shutdown(wait=wait)
    logger.info("APScheduler 调度器已关闭")


def load_scheduled_tasks_from_db():
    """从数据库加载启用的定时任务配置"""
    from app.models.cron_config import CronConfig

    db = SessionLocal()
    try:
        configs = CronConfig.get_enabled_configs(db)
        logger.info(f"从数据库加载了 {len(configs)} 个启用的定时任务配置")

        for config in configs:
            try:
                add_or_update_job_from_config(config)
            except Exception as e:
                logger.error(f"加载定时任务 '{config.task_name}' 失败: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"从数据库加载定时任务失败: {e}", exc_info=True)
    finally:
        db.close()


def add_or_update_job_from_config(config):
    """根据CronConfig添加或更新任务"""
    from app.models.cron_config import CronConfig

    scheduler = get_scheduler()

    # 映射任务名称到实际的执行函数
    task_functions = {
        'crawl_sources': scheduled_crawl_sources,
        'event_groups': scheduled_event_groups,
        'cache_cleanup': scheduled_cache_cleanup,
    }

    func = task_functions.get(config.task_name)
    if func is None:
        logger.warning(f"未知的任务类型: {config.task_name}")
        return

    job_id = f"cron_{config.task_name}"

    try:
        # 解析cron表达式
        # APScheduler CronTrigger 格式: second minute hour day month day_of_week
        # 标准cron格式: minute hour day month day_of_week
        # 需要在前面加上 second
        parts = config.cron_expression.split()
        if len(parts) == 5:
            # 标准5段cron表达式，添加秒字段
            cron_parts = ['0'] + parts  # 默认在0秒执行
        elif len(parts) == 6:
            # 已经包含秒字段
            cron_parts = parts
        else:
            logger.error(f"无效的cron表达式: {config.cron_expression}")
            return

        trigger = CronTrigger(
            second=cron_parts[0],
            minute=cron_parts[1],
            hour=cron_parts[2],
            day=cron_parts[3],
            month=cron_parts[4],
            day_of_week=cron_parts[5],
            timezone='Asia/Shanghai'
        )

        # 检查任务是否已存在
        existing_job = scheduler.get_job(job_id)
        if existing_job:
            # 更新现有任务
            scheduler.reschedule_job(job_id, trigger=trigger)
            logger.info(f"已更新定时任务: {config.task_name} (cron: {config.cron_expression})")
        else:
            # 添加新任务
            scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                name=config.description or config.task_name,
                replace_existing=True
            )
            logger.info(f"已添加定时任务: {config.task_name} (cron: {config.cron_expression})")

    except Exception as e:
        logger.error(f"添加/更新定时任务 '{config.task_name}' 失败: {e}", exc_info=True)


def remove_job(task_name: str):
    """移除定时任务"""
    scheduler = get_scheduler()
    job_id = f"cron_{task_name}"

    try:
        scheduler.remove_job(job_id)
        logger.info(f"已移除定时任务: {task_name}")
    except Exception as e:
        logger.warning(f"移除定时任务 '{task_name}' 失败: {e}")


# ===========================================
# 定时任务执行函数
# ===========================================

def scheduled_crawl_sources():
    """定时执行新闻源抓取任务"""
    logger.info("定时任务触发: 新闻源抓取")

    try:
        # 导入执行函数
        from app.services.crawl_tasks import execute_crawl_sources_task

        # 在当前线程中执行（由APScheduler管理）
        execute_crawl_sources_task()

    except Exception as e:
        logger.error(f"定时抓取任务执行失败: {e}", exc_info=True)


def scheduled_event_groups():
    """定时执行事件分组任务"""
    logger.info("定时任务触发: 事件分组")

    try:
        from app.services.event_group_tasks import execute_event_groups_task
        execute_event_groups_task()
    except Exception as e:
        logger.error(f"定时事件分组任务执行失败: {e}", exc_info=True)


def scheduled_cache_cleanup():
    """定时执行缓存清理任务"""
    logger.info("定时任务触发: 缓存清理")

    try:
        from app.services.cache_cleanup_tasks import execute_cache_cleanup_task
        execute_cache_cleanup_task()
    except Exception as e:
        logger.error(f"定时缓存清理任务执行失败: {e}", exc_info=True)


# ===========================================
# 手动触发任务（API调用）
# ===========================================

def trigger_crawl_sources_manual() -> int:
    """手动触发新闻源抓取任务，返回execution_id"""
    from app.services.crawl_tasks import execute_crawl_sources_task

    logger.info("手动触发: 新闻源抓取任务")
    return execute_crawl_sources_task()


def trigger_event_groups_manual() -> int:
    """手动触发事件分组任务，返回execution_id"""
    from app.services.event_group_tasks import execute_event_groups_task

    logger.info("手动触发: 事件分组任务")
    return execute_event_groups_task()


def trigger_cache_cleanup_manual() -> int:
    """手动触发缓存清理任务，返回execution_id"""
    from app.services.cache_cleanup_tasks import execute_cache_cleanup_task

    logger.info("手动触发: 缓存清理任务")
    return execute_cache_cleanup_task()
