"""
数据库迁移：添加cron_configs表
"""
import logging
from sqlalchemy import create_engine, inspect, Table, Column, Integer, String, DateTime, Boolean, Text, MetaData
from datetime import datetime
import os

from app.db.session import engine
from app.models.cron_config import CronConfig

logger = logging.getLogger(__name__)


def migration_add_cron_config():
    """添加cron_configs表"""
    inspector = inspect(engine)
    
    # 检查表是否已存在
    if 'cron_configs' in inspector.get_table_names():
        logger.info("cron_configs表已存在，跳过创建")
        return
    
    try:
        # 创建表
        from app.db.base import Base
        CronConfig.__table__.create(engine, checkfirst=True)
        logger.info("✓ 成功创建cron_configs表")
        
        # 插入默认配置
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            default_configs = [
                CronConfig(
                    task_name='crawl_sources',
                    cron_expression='0 */1 * * *',
                    enabled=True,
                    description='新闻源抓取任务 - 每小时执行一次'
                ),
                CronConfig(
                    task_name='event_groups',
                    cron_expression='30 */1 * * *',
                    enabled=True,
                    description='事件分组任务 - 每小时执行一次（错开抓取任务）'
                ),
                CronConfig(
                    task_name='cache_cleanup',
                    cron_expression='0 2 * * *',
                    enabled=True,
                    description='缓存清理任务 - 每天凌晨2点执行'
                )
            ]
            
            for config in default_configs:
                db.add(config)
            
            db.commit()
            logger.info(f"✓ 成功插入 {len(default_configs)} 条默认cron配置")
            
        except Exception as e:
            db.rollback()
            logger.error(f"插入默认配置失败: {str(e)}")
            raise
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"创建cron_configs表失败: {str(e)}")
        raise


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    migration_add_cron_config()

