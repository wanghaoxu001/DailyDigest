"""
添加重复检测状态字段到快报表
"""

def upgrade(db_path: str):
    """应用迁移"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 添加重复检测状态字段
        cursor.execute("""
            ALTER TABLE digests
            ADD COLUMN duplicate_detection_status VARCHAR(20) DEFAULT 'pending' NOT NULL
        """)

        # 为现有快报设置默认状态
        cursor.execute("""
            UPDATE digests
            SET duplicate_detection_status = 'pending'
            WHERE duplicate_detection_status IS NULL
        """)

        conn.commit()
        print("✅ 已添加重复检测状态字段")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⚠️  重复检测状态字段已存在，跳过迁移")
        else:
            raise e
    finally:
        conn.close()


def downgrade(db_path: str):
    """回滚迁移"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # SQLite不支持DROP COLUMN，需要重建表
        cursor.execute("PRAGMA foreign_keys=OFF")

        # 创建临时表
        cursor.execute("""
            CREATE TABLE digests_temp AS
            SELECT id, title, date, content, pdf_path, news_counts, created_at, updated_at
            FROM digests
        """)

        # 删除原表
        cursor.execute("DROP TABLE digests")

        # 重命名临时表
        cursor.execute("ALTER TABLE digests_temp RENAME TO digests")

        cursor.execute("PRAGMA foreign_keys=ON")

        conn.commit()
        print("✅ 已回滚重复检测状态字段")

    except Exception as e:
        print(f"❌ 回滚失败: {e}")
        raise e
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        upgrade(sys.argv[1])
    else:
        upgrade("/app/daily_digest.db")