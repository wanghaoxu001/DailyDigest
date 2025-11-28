"""
缓存清理任务业务逻辑
从原有的 scripts/cron_jobs/cache_cleanup_job.py 重构而来
"""
import traceback
from datetime import datetime, timedelta
from typing import Optional

from app.config import get_logger
from app.db.session import SessionLocal
from app.models.task_execution import TaskExecution
from app.services.task_execution_service import task_execution_service

logger = get_logger(__name__)


def execute_cache_cleanup_task(trigger_message: str = "任务触发") -> Optional[int]:
    """
    执行缓存清理任务的核心业务逻辑

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
        logger.info(f"开始执行缓存清理任务: {trigger_message}")
        logger.info("=" * 60)

        # 尝试获取任务锁（避免并发执行）
        execution = TaskExecution.acquire_lock(
            db,
            'cache_cleanup',
            trigger_message
        )

        if not execution:
            logger.warning("缓存清理任务已在运行中，跳过本次执行")
            return None

        execution_id = execution.id
        logger.info(f"任务已启动，执行记录ID: {execution_id}")

        # 执行实际的清理逻辑
        _execute_cache_cleanup_logic(execution_id)

        logger.info("缓存清理任务执行完成")
        return execution_id

    except Exception as e:
        error_msg = f"缓存清理任务执行失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())

        if execution:
            task_execution_service.fail_task(
                execution.id,
                error_msg,
                error_type='CacheCleanupError',
                stack_trace=traceback.format_exc()
            )

        raise  # 重新抛出异常，让调用者知道任务失败

    finally:
        db.close()


def _execute_cache_cleanup_logic(execution_id: int):
    """
    执行缓存清理逻辑的内部函数

    Args:
        execution_id: TaskExecution记录的ID
    """
    db = SessionLocal()
    try:
        start_time = datetime.now()

        # 1. 清理过期的任务执行记录
        logger.info("正在清理过期的任务执行记录...")
        task_execution_service.update_task_progress(
            execution_id, 1, 1, "正在清理过期的任务执行记录..."
        )

        cleaned_executions = task_execution_service.cleanup_old_records()
        logger.info(f"清理了 {cleaned_executions} 条过期的任务执行记录")

        # 完成任务
        execution_time = (datetime.now() - start_time).total_seconds()
        message = f"缓存清理完成，用时: {execution_time:.2f}秒，清理了 {cleaned_executions} 条任务执行记录"
        logger.info(message)

        task_execution_service.complete_task(
            execution_id,
            'success',
            message,
            {
                'deleted_task_executions': cleaned_executions
            },
            cleaned_executions,
            cleaned_executions,
            0
        )

    except Exception as e:
        db.rollback()
        logger.error(f"执行缓存清理逻辑时出错: {e}", exc_info=True)
        raise
    finally:
        db.close()
