import sqlite3
import logging
import json

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path):
    """向news表添加tokens_usage列，用于存储LLM调用消耗的tokens信息"""
    logger.info(f"开始执行迁移: 添加tokens_usage列到news表")

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(news)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        # 添加新列
        if "tokens_usage" not in column_names:
            logger.info("添加tokens_usage列到news表")
            cursor.execute("ALTER TABLE news ADD COLUMN tokens_usage TEXT")

            # 初始化所有现有记录的新列
            cursor.execute("UPDATE news SET tokens_usage = '{}'")
            conn.commit()
            logger.info("成功添加tokens_usage列")
        else:
            logger.info("tokens_usage列已存在，无需添加")

        # 关闭连接
        conn.close()
        return True
    except Exception as e:
        logger.error(f"执行迁移时出错: {str(e)}")
        return False


if __name__ == "__main__":
    run_migration("daily_digest.db")
