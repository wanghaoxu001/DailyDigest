#!/usr/bin/env python3
"""
缓存清理定时任务
通过系统cron调度执行
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import logging
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量（必须在导入其他模块之前）
load_dotenv()

# 设置环境变量
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from app.config import setup_logging, get_logger
from app.config.log_forwarder import ExternalLogForwardHandler, build_forward_handler_from_env

setup_logging(enable_buffer=False)
logger = get_logger('scripts.cron_jobs.cache_cleanup_job')

forward_handler = build_forward_handler_from_env()
if forward_handler is None:
    default_endpoint = os.getenv(
        "LOG_FORWARD_DEFAULT_ENDPOINT",
        "http://127.0.0.1:18899/api/logs/ingest",
    )
    if default_endpoint:
        forward_handler = ExternalLogForwardHandler(default_endpoint)

if forward_handler:
    forward_handler.setLevel(logging.INFO)
    logger.addHandler(forward_handler)

from app.db.session import SessionLocal
from app.models.task_execution import TaskExecution
from app.services.task_execution_service import task_execution_service


def execute_cache_cleanup(execution_id: int):
    """执行缓存清理逻辑"""
    db = SessionLocal()
    try:
        logger.info("正在清理过期缓存记录...")
        task_execution_service.update_task_progress(
            execution_id, 1, 2, "正在清理过期的任务执行记录..."
        )

        start_time = datetime.now()

        # 清理过期的任务执行记录
        logger.info("正在清理过期的任务执行记录...")

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
        raise
    finally:
        db.close()


def main():
    """主函数"""
    db = SessionLocal()
    execution = None
    
    try:
        logger.info("=" * 60)
        logger.info("开始执行缓存清理任务")
        logger.info("=" * 60)
        
        # 尝试获取任务锁
        execution = TaskExecution.acquire_lock(
            db,
            'cache_cleanup',
            '定时任务：开始执行缓存清理'
        )
        
        if not execution:
            logger.warning("缓存清理任务已在运行中，跳过本次执行")
            print("任务已在运行中，跳过")
            sys.exit(0)
        
        execution_id = execution.id
        logger.info(f"任务已启动，执行记录ID: {execution_id}")
        
        # 执行清理逻辑
        execute_cache_cleanup(execution_id)
        
        logger.info("缓存清理任务执行完成")
        
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
        
        sys.exit(1)
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
