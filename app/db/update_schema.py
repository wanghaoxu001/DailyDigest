import sqlite3
import logging
import os
import json
from pathlib import Path

# 导入迁移脚本
from app.db.migrations.add_newspaper_keywords import (
    run_migration as run_add_newspaper_keywords,
)
from app.db.migrations.add_article_summary import (
    run_migration as run_add_article_summary,
)
from app.db.migrations.add_tokens_usage import run_migration as run_add_tokens_usage
from app.db.migrations.add_use_rss_summary import (
    run_migration as run_add_use_rss_summary,
)
from app.db.migrations.add_use_newspaper import run_migration as run_add_use_newspaper
from app.db.migrations.add_max_fetch_days import migrate_add_max_fetch_days

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_sources_table():
    """更新sources表，添加抓取状态和结果字段"""
    # 获取数据库文件路径
    db_path = os.environ.get("DATABASE_URL", "daily_digest.db")

    # 如果数据库路径是SQLAlchemy URL，则提取文件路径
    if db_path.startswith("sqlite:///"):
        db_path = db_path[10:]

    # 确保数据库存在
    if not Path(db_path).exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return False

    logger.info(f"开始更新数据库: {db_path}")

    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查列是否已存在
        cursor.execute("PRAGMA table_info(sources)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]

        # 添加新列
        changes_made = False

        if "last_fetch_status" not in column_names:
            logger.info("添加 last_fetch_status 列")
            cursor.execute("ALTER TABLE sources ADD COLUMN last_fetch_status TEXT")
            changes_made = True

        if "last_fetch_result" not in column_names:
            logger.info("添加 last_fetch_result 列")
            cursor.execute("ALTER TABLE sources ADD COLUMN last_fetch_result TEXT")
            changes_made = True

        # 如果进行了更改，提交事务
        if changes_made:
            # 初始化所有现有记录的新列
            cursor.execute(
                "UPDATE sources SET last_fetch_status = 'unknown', last_fetch_result = '{}'"
            )
            conn.commit()
            logger.info("数据库更新成功")
        else:
            logger.info("数据库结构已是最新，无需更改")

        # 关闭连接
        conn.close()
        return True

    except Exception as e:
        logger.error(f"更新数据库时出错: {str(e)}")
        return False


def run_migrations():
    """执行所有数据库迁移脚本"""
    logger.info("开始执行数据库迁移...")

    # 获取数据库文件路径
    db_path = os.environ.get("DATABASE_URL", "daily_digest.db")

    # 如果数据库路径是SQLAlchemy URL，则提取文件路径
    if db_path.startswith("sqlite:///"):
        db_path = db_path[10:]

    # 确保数据库存在
    if not Path(db_path).exists():
        logger.error(f"数据库文件不存在: {db_path}")
        return False

    # 执行所有迁移脚本
    try:
        # 添加newspaper_keywords字段
        run_add_newspaper_keywords(db_path)

        # 添加article_summary字段
        run_add_article_summary(db_path)

        # 添加tokens_usage字段
        run_add_tokens_usage(db_path)

        # 添加use_rss_summary字段
        run_add_use_rss_summary(db_path)

        # 添加use_newspaper字段
        run_add_use_newspaper(db_path)

        # 添加max_fetch_days字段
        migrate_add_max_fetch_days(db_path)

        logger.info("所有迁移脚本执行完成")
        return True
    except Exception as e:
        logger.error(f"执行迁移脚本时出错: {str(e)}")
        return False


if __name__ == "__main__":
    update_sources_table()
    run_migrations()
