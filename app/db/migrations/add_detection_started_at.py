import sqlite3
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path):
    """添加 duplicate_detection_started_at 字段到 digests 表"""
    logger.info(f"开始执行迁移: 添加duplicate_detection_started_at字段到digests表")

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(digests)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        # 添加新列
        if "duplicate_detection_started_at" not in column_names:
            logger.info("添加duplicate_detection_started_at字段到digests表")
            cursor.execute("ALTER TABLE digests ADD COLUMN duplicate_detection_started_at DATETIME NULL")
            conn.commit()
            logger.info("成功添加duplicate_detection_started_at字段")
        else:
            logger.info("duplicate_detection_started_at字段已存在，跳过添加")

        # 关闭连接
        conn.close()
        return True
    except Exception as e:
        logger.error(f"执行迁移时出错: {str(e)}")
        return False


if __name__ == "__main__":
    run_migration("daily_digest.db")