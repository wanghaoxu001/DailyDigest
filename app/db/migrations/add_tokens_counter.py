"""
添加tokens_used字段到sources表
"""
import sqlite3
import logging
from sqlalchemy import create_engine, MetaData, Table

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metadata = MetaData()


def migrate(connection):
    # 获取sources表
    sources = Table("sources", metadata, autoload_with=connection)

    # 检查字段是否已存在
    if "tokens_used" not in sources.c:
        # 添加tokens_used字段
        connection.execute(
            """
            ALTER TABLE sources
            ADD COLUMN tokens_used INTEGER DEFAULT 0;
            """
        )
        logger.info("已添加tokens_used字段到sources表")
        return True
    else:
        logger.info("tokens_used字段已存在，无需迁移")
        return False

    # 提交事务
    connection.commit()


def run_migration(db_path="daily_digest.db"):
    """
    运行迁移脚本
    
    参数:
    - db_path: 数据库文件路径
    
    返回:
    - 布尔值，表示是否执行了迁移
    """
    logger.info("开始执行添加tokens_used字段的迁移...")
    
    try:
        # 创建数据库连接
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as connection:
            # 执行迁移
            result = migrate(connection)
            return result
    except Exception as e:
        logger.error(f"迁移执行失败: {str(e)}")
        return False 