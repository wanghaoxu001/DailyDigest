"""
添加重复检测结果表和相关字段
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.sql import func
from app.db.base import Base


def upgrade(db_path):
    """升级数据库结构"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 创建重复检测结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS duplicate_detection_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_id INTEGER NOT NULL,
                news_id INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'checking',
                duplicate_with_news_id INTEGER NULL,
                similarity_score FLOAT NULL,
                llm_reasoning TEXT NULL,
                checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (digest_id) REFERENCES digests (id),
                FOREIGN KEY (news_id) REFERENCES news (id),
                FOREIGN KEY (duplicate_with_news_id) REFERENCES news (id)
            )
        """)

        # 创建索引以提高查询性能
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_duplicate_detection_digest_id
            ON duplicate_detection_results (digest_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_duplicate_detection_news_id
            ON duplicate_detection_results (news_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_duplicate_detection_status
            ON duplicate_detection_results (status)
        """)

        conn.commit()
        print("重复检测结果表已创建")

    except Exception as e:
        conn.rollback()
        print(f"创建重复检测结果表失败: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path):
    """降级数据库结构"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 删除索引
        cursor.execute("DROP INDEX IF EXISTS idx_duplicate_detection_status")
        cursor.execute("DROP INDEX IF EXISTS idx_duplicate_detection_news_id")
        cursor.execute("DROP INDEX IF EXISTS idx_duplicate_detection_digest_id")

        # 删除表
        cursor.execute("DROP TABLE IF EXISTS duplicate_detection_results")

        conn.commit()
        print("重复检测结果表已删除")

    except Exception as e:
        conn.rollback()
        print(f"删除重复检测结果表失败: {e}")
        raise
    finally:
        conn.close()


# 为了兼容现有迁移系统
def run_migration(db_path):
    upgrade(db_path)