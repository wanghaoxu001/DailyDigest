"""
添加prompt_tokens和completion_tokens字段到sources表
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
    fields_to_add = []
    if "prompt_tokens" not in sources.c:
        fields_to_add.append("prompt_tokens INTEGER DEFAULT 0")
    if "completion_tokens" not in sources.c:
        fields_to_add.append("completion_tokens INTEGER DEFAULT 0")

    if fields_to_add:
        # 添加字段
        for field in fields_to_add:
            connection.execute(f"ALTER TABLE sources ADD COLUMN {field}")
        
        logger.info(f"已添加字段到sources表: {', '.join(fields_to_add)}")
        
        # 如果tokens_used已有数据，将其均分到prompt_tokens和completion_tokens
        connection.execute("""
            UPDATE sources 
            SET prompt_tokens = CAST(tokens_used * 0.7 AS INTEGER), 
                completion_tokens = CAST(tokens_used * 0.3 AS INTEGER) 
            WHERE tokens_used > 0
        """)
        logger.info("已将现有tokens_used数据分配到prompt_tokens和completion_tokens")
        
        return True
    else:
        logger.info("prompt_tokens和completion_tokens字段已存在，无需迁移")
        return False


def run_migration(db_path="daily_digest.db"):
    """
    运行迁移脚本
    
    参数:
    - db_path: 数据库文件路径
    
    返回:
    - 布尔值，表示是否执行了迁移
    """
    logger.info("开始执行添加详细token字段的迁移...")
    
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