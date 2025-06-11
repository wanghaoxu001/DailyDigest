#!/usr/bin/env python3
"""
清空数据库中的新闻记录
"""

import sys
import os
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 确保能导入应用模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入模型
from app.db.session import engine, SessionLocal
from app.models.news import News


def clear_all_news():
    """删除数据库中的所有新闻记录"""
    db = SessionLocal()
    try:
        # 获取当前新闻数量
        count = db.query(News).count()
        print(f"当前数据库中有 {count} 条新闻记录")

        # 删除所有新闻记录
        db.query(News).delete()
        db.commit()
        print(f"已成功删除所有 {count} 条新闻记录")
        return count
    except Exception as e:
        db.rollback()
        print(f"删除新闻记录时出错: {str(e)}")
        return 0
    finally:
        db.close()


def clear_news_direct_sql():
    """使用直接SQL语句删除所有新闻记录（备用方法）"""
    try:
        # 假设SQLite数据库文件在项目根目录
        db_path = "daily_digest.db"
        if not os.path.exists(db_path):
            print(f"数据库文件 {db_path} 不存在")
            return 0

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 获取当前记录数
        cursor.execute("SELECT COUNT(*) FROM news")
        count = cursor.fetchone()[0]
        print(f"当前数据库中有 {count} 条新闻记录")

        # 删除所有记录
        cursor.execute("DELETE FROM news")
        conn.commit()

        print(f"已成功删除所有 {count} 条新闻记录")
        return count
    except Exception as e:
        print(f"直接SQL删除新闻记录时出错: {str(e)}")
        return 0
    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    print("开始清空新闻记录...")

    # 尝试使用SQLAlchemy删除
    count = clear_all_news()

    # 如果SQLAlchemy方法失败，则尝试直接SQL
    if count == 0:
        print("尝试使用直接SQL方法删除...")
        count = clear_news_direct_sql()

    print(f"操作完成，共删除 {count} 条新闻记录")
