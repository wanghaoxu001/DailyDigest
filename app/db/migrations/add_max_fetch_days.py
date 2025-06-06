"""
添加max_fetch_days列到sources表的迁移脚本
创建时间: 2024-12-19
"""

import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def migrate_add_max_fetch_days(db_path: str) -> bool:
    """
    为sources表添加max_fetch_days列
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        bool: 迁移是否成功
    """
    logger.info(f"开始执行迁移: 添加max_fetch_days字段到sources表 (数据库: {db_path})")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(sources)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'max_fetch_days' in columns:
            logger.info("max_fetch_days 字段已存在，跳过迁移")
            return True
        
        # 添加max_fetch_days字段，默认值为7天
        cursor.execute("""
            ALTER TABLE sources 
            ADD COLUMN max_fetch_days INTEGER DEFAULT 7
        """)
        
        # 为现有记录设置默认值
        cursor.execute("""
            UPDATE sources 
            SET max_fetch_days = 7 
            WHERE max_fetch_days IS NULL
        """)
        
        conn.commit()
        logger.info("max_fetch_days字段添加成功")
        
        return True
        
    except Exception as e:
        logger.error(f"添加max_fetch_days字段失败: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return False
        
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    # 可以直接运行此脚本进行迁移
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "./daily_digest.db"
    
    success = migrate_add_max_fetch_days(db_path)
    if success:
        print("迁移成功完成")
    else:
        print("迁移失败")
        sys.exit(1) 