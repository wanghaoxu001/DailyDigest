"""
为sources.id启用AUTOINCREMENT，避免删除后新增复用旧ID
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


CREATE_TABLE_SQL = """
CREATE TABLE sources_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    url VARCHAR(500) NOT NULL,
    type VARCHAR(7) NOT NULL,
    active BOOLEAN,
    last_fetch DATETIME,
    fetch_interval INTEGER,
    xpath_config TEXT,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    last_fetch_status TEXT,
    last_fetch_result TEXT,
    use_rss_summary BOOLEAN DEFAULT 1,
    use_newspaper BOOLEAN DEFAULT 1,
    tokens_used INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    max_fetch_days INTEGER DEFAULT 7,
    use_description_as_summary BOOLEAN DEFAULT 0
);
"""

COPY_DATA_SQL = """
INSERT INTO sources_new (
    id,
    name,
    url,
    type,
    active,
    last_fetch,
    fetch_interval,
    xpath_config,
    description,
    created_at,
    updated_at,
    last_fetch_status,
    last_fetch_result,
    use_rss_summary,
    use_newspaper,
    tokens_used,
    prompt_tokens,
    completion_tokens,
    max_fetch_days,
    use_description_as_summary
)
SELECT
    id,
    name,
    url,
    type,
    active,
    last_fetch,
    fetch_interval,
    xpath_config,
    description,
    created_at,
    updated_at,
    last_fetch_status,
    last_fetch_result,
    use_rss_summary,
    use_newspaper,
    tokens_used,
    prompt_tokens,
    completion_tokens,
    max_fetch_days,
    use_description_as_summary
FROM sources;
"""


def _needs_migration(cursor) -> bool:
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='sources';"
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        logger.warning("未找到sources表，跳过AUTOINCREMENT迁移")
        return False
    return "AUTOINCREMENT" not in row[0].upper()


def _update_sqlite_sequence(cursor):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence';"
    )
    has_sequence = cursor.fetchone() is not None
    if not has_sequence:
        return

    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM sources;")
    max_id = cursor.fetchone()[0] or 0

    # 考虑仍然存在的引用（如news表中的source_id）
    reference_queries = [
        "SELECT COALESCE(MAX(source_id), 0) FROM news;"
    ]

    for query in reference_queries:
        try:
            cursor.execute(query)
            value = cursor.fetchone()[0] or 0
            if value > max_id:
                max_id = value
        except sqlite3.OperationalError:
            # 目标表不存在时忽略
            continue

    cursor.execute(
        "SELECT COUNT(*) FROM sqlite_sequence WHERE name='sources';"
    )
    exists = cursor.fetchone()[0] > 0

    if exists:
        cursor.execute(
            "UPDATE sqlite_sequence SET seq=? WHERE name='sources';", (max_id,)
        )
    else:
        cursor.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES ('sources', ?);",
            (max_id,),
        )


def run_migration(db_path="daily_digest.db") -> bool:
    """
    运行迁移，确保sources.id不再复用

    返回:
        bool: 是否执行了迁移
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        if not _needs_migration(cursor):
            logger.info("sources表已启用AUTOINCREMENT，跳过迁移")
            return False

        logger.info("开始执行sources AUTOINCREMENT迁移")

        cursor.execute("PRAGMA foreign_keys=OFF;")
        cursor.execute("BEGIN;")

        try:
            cursor.execute(CREATE_TABLE_SQL)
            cursor.execute(COPY_DATA_SQL)
            cursor.execute("DROP TABLE sources;")
            cursor.execute("ALTER TABLE sources_new RENAME TO sources;")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_sources_id ON sources (id);"
            )
            _update_sqlite_sequence(cursor)
            conn.commit()
            logger.info("sources表已重建并启用AUTOINCREMENT")
        except Exception as exc:
            conn.rollback()
            logger.error("sources AUTOINCREMENT迁移失败，已回滚", exc_info=True)
            raise exc
        finally:
            cursor.execute("PRAGMA foreign_keys=ON;")

        return True
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
