#!/usr/bin/env python3
"""
事件分组定时任务
通过系统cron调度执行
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量（必须在导入其他模块之前）
load_dotenv()

# 设置环境变量
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from app.config import setup_logging, get_logger
from app.config.log_forwarder import ExternalLogForwardHandler, build_forward_handler_from_env

setup_logging(enable_buffer=False)
logger = get_logger('scripts.cron_jobs.event_groups_job')

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


def execute_event_groups(execution_id: int, use_multiprocess: bool = True):
    """执行事件分组逻辑"""
    from app.services.news_similarity_storage import news_similarity_storage_service
    from app.services.event_group_cache import event_group_cache_service
    
    db = SessionLocal()
    try:
        start_time = datetime.now()
        
        # 1. 计算并存储相似度（最近48小时的新闻）
        logger.info("正在计算并存储新闻相似度...")
        task_execution_service.update_task_progress(
            execution_id, 10, 100, "正在计算并存储新闻相似度..."
        )
        
        # 定义进度回调函数
        def similarity_progress_callback(message: str, current: int, total: int, details: dict = None):
            # 相似度计算占总进度的70%
            progress = 10 + int((current / total) * 70) if total > 0 else 10
            task_execution_service.update_task_progress(
                execution_id, progress, 100, message
            )
        
        similarity_result = news_similarity_storage_service.compute_and_store_similarities(
            db=db, 
            hours=48, 
            force_recalculate=False,
            progress_callback=similarity_progress_callback,
            use_multiprocess=use_multiprocess
        )
        
        logger.info(f"相似度计算完成: {similarity_result}")
        
        # 2. 计算并存储事件分组（最近48小时的新闻）
        task_execution_service.update_task_progress(
            execution_id, 80, 100, "正在计算并存储事件分组..."
        )
        logger.info("正在计算并存储事件分组...")
        
        groups_result = news_similarity_storage_service.compute_and_store_event_groups(
            db=db,
            hours=48,
            force_recalculate=False
        )
        
        logger.info(f"事件分组计算完成: {groups_result}")
        
        # 3. 清理旧的相似度记录（保留7天）
        task_execution_service.update_task_progress(
            execution_id, 90, 100, "正在清理旧的相似度记录..."
        )
        logger.info("正在清理旧的相似度记录...")
        
        cleanup_result = news_similarity_storage_service.cleanup_old_similarities(
            db=db,
            days=7
        )
        
        logger.info(f"清理了 {cleanup_result} 条旧记录")
        
        # 4. 生成事件分组缓存
        task_execution_service.update_task_progress(
            execution_id, 95, 100, "正在生成事件分组缓存..."
        )
        logger.info("正在生成事件分组缓存...")
        
        cache_total_groups = 0
        common_configurations = [
            {'hours': 24, 'exclude_used': True},
            {'hours': 48, 'exclude_used': True},
            {'hours': 24, 'exclude_used': False}
        ]
        
        for config in common_configurations:
            try:
                groups = event_group_cache_service.get_or_generate_groups(
                    db=db,
                    hours=config['hours'],
                    categories=['金融业网络安全事件', '重大网络安全事件', '重大数据泄露事件', '重大漏洞风险提示', '其他'],
                    source_ids=None,
                    exclude_used=config['exclude_used'],
                    force_refresh=True
                )
                cache_total_groups += len(groups)
                logger.info(f"成功预生成事件分组缓存: {len(groups)}个组 (hours={config['hours']}, exclude_used={config['exclude_used']})")
            except Exception as e:
                logger.error(f"预生成事件分组缓存失败 {config}: {str(e)}")
        
        # 完成任务
        execution_time = (datetime.now() - start_time).total_seconds()
        method = "多进程" if use_multiprocess else "单进程"
        message = (
            f"相似度和分组计算完成（{method}），用时: {execution_time:.2f}秒，"
            f"新相似度: {similarity_result.get('new_similarities', 0)}条，"
            f"新分组: {groups_result.get('groups_created', 0)}个，"
            f"缓存分组: {cache_total_groups}个，"
            f"清理记录: {cleanup_result}条"
        )
        logger.info(message)
        
        task_execution_service.complete_task(
            execution_id,
            'success',
            message,
            {
                'similarity_result': similarity_result,
                'groups_result': groups_result,
                'cache_total_groups': cache_total_groups,
                'cleanup_result': cleanup_result,
                'use_multiprocess': use_multiprocess
            },
            similarity_result.get('new_similarities', 0) + groups_result.get('groups_created', 0),
            similarity_result.get('new_similarities', 0) + groups_result.get('groups_created', 0),
            0
        )
        
    finally:
        db.close()


def main():
    """主函数"""
    db = SessionLocal()
    execution = None
    
    try:
        logger.info("=" * 60)
        logger.info("开始执行事件分组任务")
        logger.info("=" * 60)
        
        # 从环境变量读取是否使用多进程
        use_multiprocess = os.getenv('USE_MULTIPROCESS', 'true').lower() == 'true'
        logger.info(f"使用{'多进程' if use_multiprocess else '单进程'}计算")
        
        # 尝试获取任务锁
        execution = TaskExecution.acquire_lock(
            db,
            'event_groups',
            f"定时任务：开始执行事件分组任务（{'多进程' if use_multiprocess else '单进程'}）"
        )
        
        if not execution:
            logger.warning("事件分组任务已在运行中，跳过本次执行")
            print("任务已在运行中，跳过")
            sys.exit(0)
        
        execution_id = execution.id
        logger.info(f"任务已启动，执行记录ID: {execution_id}")
        
        # 执行事件分组逻辑
        execute_event_groups(execution_id, use_multiprocess)
        
        logger.info("事件分组任务执行完成")
        
    except Exception as e:
        error_msg = f"事件分组任务执行失败: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        if execution:
            task_execution_service.fail_task(
                execution.id,
                error_msg,
                error_type='EventGroupsError',
                stack_trace=traceback.format_exc()
            )
        
        sys.exit(1)
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
