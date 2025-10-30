#!/usr/bin/env python3
"""
初始化cron配置
在数据库中创建默认的cron配置
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import SessionLocal
from app.models.cron_config import CronConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_cron_configs():
    """初始化默认cron配置"""
    db = SessionLocal()
    try:
        # 检查是否已有配置
        existing_count = db.query(CronConfig).count()
        if existing_count > 0:
            logger.info(f"数据库中已有 {existing_count} 个cron配置，跳过初始化")
            return
        
        # 创建默认配置
        default_configs = [
            {
                'task_name': 'crawl_sources',
                'cron_expression': '0 */1 * * *',  # 每小时执行一次
                'enabled': True,
                'description': '新闻源抓取任务 - 每小时执行一次'
            },
            {
                'task_name': 'event_groups',
                'cron_expression': '30 */1 * * *',  # 每小时的第30分钟执行
                'enabled': True,
                'description': '事件分组任务 - 每小时执行一次（错开抓取任务）'
            },
            {
                'task_name': 'cache_cleanup',
                'cron_expression': '0 2 * * *',  # 每天凌晨2点执行
                'enabled': True,
                'description': '缓存清理任务 - 每天凌晨2点执行'
            }
        ]
        
        for config_data in default_configs:
            config = CronConfig(**config_data)
            db.add(config)
            logger.info(f"创建cron配置: {config_data['task_name']} - {config_data['cron_expression']}")
        
        db.commit()
        logger.info(f"成功初始化 {len(default_configs)} 个默认cron配置")
        
    except Exception as e:
        db.rollback()
        logger.error(f"初始化cron配置失败: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == '__main__':
    init_cron_configs()

