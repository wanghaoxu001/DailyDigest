#!/usr/bin/env python3
"""
新闻源抓取定时任务
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

# 配置日志（统一使用应用内配置，关闭缓冲）
setup_logging(enable_buffer=False)
logger = get_logger('scripts.cron_jobs.crawl_sources_job')

# 日志转发：暂时禁用以避免死锁问题
# 问题详情见: CRAWL_ISSUE_INVESTIGATION_REPORT.md
# TODO: 实施异步日志转发方案后重新启用
# forward_handler = build_forward_handler_from_env()
# if forward_handler is None:
#     default_endpoint = os.getenv(
#         "LOG_FORWARD_DEFAULT_ENDPOINT",
#         "http://127.0.0.1:18899/api/logs/ingest",
#     )
#     if default_endpoint:
#         forward_handler = ExternalLogForwardHandler(default_endpoint)
#
# if forward_handler:
#     forward_handler.setLevel(logging.INFO)
#     logger.addHandler(forward_handler)

from app.db.session import SessionLocal
from app.models.task_execution import TaskExecution
from app.services.task_execution_service import task_execution_service


def execute_crawl_sources(execution_id: int):
    """执行新闻源抓取逻辑"""
    from app.services.crawler import crawl_source
    from app.models.source import Source
    
    db = SessionLocal()
    try:
        logger.info("正在获取活跃的新闻源列表...")
        task_execution_service.update_task_progress(
            execution_id, 0, 100, "正在获取活跃的新闻源列表..."
        )
        
        # 获取所有活跃的源
        active_sources = db.query(Source).filter(Source.active == True).all()
        logger.info(f"找到 {len(active_sources)} 个活跃新闻源")
        
        total_processed = 0
        successful_crawls = 0
        skipped_sources = 0
        failed_sources = 0
        
        for i, source in enumerate(active_sources, 1):
            try:
                # 检查是否需要抓取
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
                logger.error(f"抓取源 '{source.name}' 时出错: {str(source_error)}")
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
        
    finally:
        db.close()


def main():
    """主函数"""
    db = SessionLocal()
    execution = None
    
    try:
        logger.info("=" * 60)
        logger.info("开始执行新闻源抓取任务")
        logger.info("=" * 60)
        
        # 尝试获取任务锁
        execution = TaskExecution.acquire_lock(
            db, 
            'crawl_sources', 
            '定时任务：开始执行新闻源抓取'
        )
        
        if not execution:
            logger.warning("新闻源抓取任务已在运行中，跳过本次执行")
            print("任务已在运行中，跳过")
            sys.exit(0)
        
        execution_id = execution.id
        logger.info(f"任务已启动，执行记录ID: {execution_id}")
        
        # 执行抓取逻辑
        execute_crawl_sources(execution_id)
        
        logger.info("新闻源抓取任务执行完成")
        
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
        
        sys.exit(1)
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
