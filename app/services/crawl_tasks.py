"""
新闻源抓取任务业务逻辑
从原有的 scripts/cron_jobs/crawl_sources_job.py 重构而来
现在在主进程中执行，可以共享资源和统一管理
"""
import traceback
from datetime import datetime
from typing import Optional

from app.config import get_logger
from app.db.session import SessionLocal
from app.models.task_execution import TaskExecution
from app.models.source import Source
from app.services.task_execution_service import task_execution_service
from app.services.crawler import crawl_source

logger = get_logger(__name__)


def execute_crawl_sources_task(trigger_message: str = "任务触发") -> Optional[int]:
    """
    执行新闻源抓取任务的核心业务逻辑

    这个函数可以被以下方式调用:
    1. APScheduler定时任务调度
    2. FastAPI BackgroundTasks手动触发
    3. 直接函数调用（测试）

    Args:
        trigger_message: 任务触发来源说明

    Returns:
        执行记录ID (execution_id)，如果任务已在运行则返回None
    """
    db = SessionLocal()
    execution = None

    try:
        logger.info("=" * 60)
        logger.info(f"开始执行新闻源抓取任务: {trigger_message}")
        logger.info("=" * 60)

        # 尝试获取任务锁（避免并发执行）
        execution = TaskExecution.acquire_lock(
            db,
            'crawl_sources',
            trigger_message
        )

        if not execution:
            logger.warning("新闻源抓取任务已在运行中，跳过本次执行")
            return None

        execution_id = execution.id
        logger.info(f"任务已启动，执行记录ID: {execution_id}")

        # 执行实际的抓取逻辑
        _execute_crawl_logic(execution_id)

        logger.info("新闻源抓取任务执行完成")
        return execution_id

    except Exception as e:
        error_msg = f"新闻源抓取任务执行失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())

        if execution:
            task_execution_service.fail_task(
                execution.id,
                error_msg,
                error_type='CrawlSourcesError',
                stack_trace=traceback.format_exc()
            )

        raise  # 重新抛出异常，让调用者知道任务失败

    finally:
        db.close()


def _execute_crawl_logic(execution_id: int):
    """
    执行抓取逻辑的内部函数

    Args:
        execution_id: TaskExecution记录的ID
    """
    db = SessionLocal()
    try:
        logger.info("正在获取活跃的新闻源列表...")
        task_execution_service.update_task_progress(
            execution_id, 0, 100, "正在获取活跃的新闻源列表..."
        )

        # 获取所有活跃的源
        active_sources = db.query(Source).filter(Source.active == True).all()
        logger.info(f"找到 {len(active_sources)} 个活跃新闻源")

        if len(active_sources) == 0:
            logger.warning("没有找到活跃的新闻源")
            task_execution_service.complete_task(
                execution_id,
                'warning',
                '没有找到活跃的新闻源',
                {},
                0, 0, 0
            )
            return

        total_processed = 0
        successful_crawls = 0
        skipped_sources = 0
        failed_sources = 0

        for i, source in enumerate(active_sources, 1):
            try:
                # 检查是否需要抓取（基于fetch_interval）
                current_time = datetime.now()
                if source.last_fetch:
                    time_since_last_crawl = (current_time - source.last_fetch).total_seconds()
                    if time_since_last_crawl < source.fetch_interval:
                        skipped_sources += 1
                        logger.info(f"跳过源: {source.name} (未到抓取时间)")
                        task_execution_service.update_task_progress(
                            execution_id, i, len(active_sources),
                            f"跳过源: {source.name} (未到抓取时间)"
                        )
                        continue

                logger.info(f"正在抓取: {source.name} ({i}/{len(active_sources)})")
                task_execution_service.update_task_progress(
                    execution_id, i, len(active_sources),
                    f"正在抓取: {source.name}"
                )

                # 执行抓取
                result = crawl_source(source.id)

                if result.get('status') == 'success':
                    successful_crawls += 1
                    logger.info(f"成功抓取源 '{source.name}': {result.get('message', '')}")
                else:
                    failed_sources += 1
                    logger.warning(f"抓取源 '{source.name}' 失败: {result.get('message', '')}")

                total_processed += 1

            except Exception as source_error:
                failed_sources += 1
                logger.error(f"抓取源 '{source.name}' 时出错: {str(source_error)}", exc_info=True)
                continue

        # 完成任务
        message = f"抓取任务完成，处理了 {total_processed} 个源，成功 {successful_crawls} 个，跳过 {skipped_sources} 个，失败 {failed_sources} 个"
        logger.info(message)

        task_execution_service.complete_task(
            execution_id,
            'success',
            message,
            {
                'total_sources': len(active_sources),
                'processed_sources': total_processed,
                'successful_crawls': successful_crawls,
                'skipped_sources': skipped_sources,
                'failed_sources': failed_sources
            },
            total_processed,
            successful_crawls,
            failed_sources
        )

    except Exception as e:
        logger.error(f"执行抓取逻辑时出错: {e}", exc_info=True)
        raise
    finally:
        db.close()
