import sqlite3
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path: str):
    """为sources表添加use_rss_summary字段的迁移脚本"""
    logger.info("开始执行迁移: 添加use_rss_summary字段到sources表")

    # 确保数据库存在
    if not Path(db_path).exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return False

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(sources)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        if "use_rss_summary" not in column_names:
            logger.info("添加 use_rss_summary 列到 sources 表")

            # 添加新列，默认值为True（参考RSS原始摘要）
            cursor.execute(
                "ALTER TABLE sources ADD COLUMN use_rss_summary BOOLEAN DEFAULT 1"
            )

            # 为现有的RSS源设置默认值为True（保持现有行为）
            cursor.execute("UPDATE sources SET use_rss_summary = 1 WHERE type = 'rss'")

            # 为网页源设置默认值为True（虽然对网页源无效，但保持一致性）
            cursor.execute(
                "UPDATE sources SET use_rss_summary = 1 WHERE type = 'webpage'"
            )

            conn.commit()
            logger.info("use_rss_summary 字段添加成功，现有RSS源已设置为使用原始摘要")
        else:
            logger.info("use_rss_summary 字段已存在，跳过迁移")

        # 关闭连接
        conn.close()
        return True

    except Exception as e:
        logger.error(f"执行迁移时出错: {str(e)}")
        if "conn" in locals():
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    import os

    db_path = os.environ.get("DATABASE_URL", "daily_digest.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[10:]
    run_migration(db_path)
