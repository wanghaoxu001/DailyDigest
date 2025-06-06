"""
迁移脚本：添加article_summary列到news表
"""

import logging
import sqlite3

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration(db_path="daily_digest.db"):
    """执行迁移添加article_summary字段"""
    logger.info(f"开始迁移：添加article_summary列到news表 (数据库: {db_path})")
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news'")
        if not cursor.fetchone():
            logger.warning("news表不存在，无需迁移")
            conn.close()
            return False
            
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(news)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "article_summary" in columns:
            logger.info("article_summary字段已存在，无需添加")
            conn.close()
            return False
            
        # 添加新字段
        logger.info("添加article_summary字段...")
        cursor.execute("ALTER TABLE news ADD COLUMN article_summary TEXT")
        
        # 提交更改
        conn.commit()
        logger.info("迁移完成：成功添加article_summary字段")
        
        # 关闭连接
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"迁移失败: {str(e)}")
        return False
        
if __name__ == "__main__":
    # 当脚本直接运行时执行迁移
    success = run_migration()
    if success:
        print("数据库迁移成功！")
    else:
        print("数据库迁移失败或不需要迁移。") 