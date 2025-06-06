"""
修复tokens字段中的小数值，转换为整数
"""
import logging
from sqlalchemy import create_engine, MetaData, Table, text

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

metadata = MetaData()


def migrate(connection):
    # 获取sources表
    sources = Table("sources", metadata, autoload_with=connection)
    
    # 使用更简单的方法直接更新所有记录
    query = text("""
        UPDATE sources 
        SET 
            prompt_tokens = CAST(prompt_tokens AS INTEGER),
            completion_tokens = CAST(completion_tokens AS INTEGER),
            tokens_used = CAST(tokens_used AS INTEGER)
    """)
    
    result = connection.execute(query)
    
    logger.info(f"已尝试修复所有源的token值")
    logger.info(f"SQL更新影响了 {result.rowcount} 条记录")
    
    return True


def run_migration(db_path="daily_digest.db"):
    """
    运行修复脚本
    
    参数:
    - db_path: 数据库文件路径
    
    返回:
    - 布尔值，表示是否执行了修复
    """
    logger.info("开始执行token小数值修复...")
    
    try:
        # 创建数据库连接
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as connection:
            # 执行迁移
            result = migrate(connection)
            return result
    except Exception as e:
        logger.error(f"修复执行失败: {str(e)}")
        return False 