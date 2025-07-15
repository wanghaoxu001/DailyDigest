import os
import sys
import sqlite3
from pathlib import Path

# 添加项目路径到Python路径
sys.path.insert(0, '/root/DailyDigest')

# 导入修复后的函数
from app.services.digest_generator import create_digest_content

# 模拟News对象
class MockNews:
    def __init__(self, id, title, generated_title, generated_summary, summary, category):
        self.id = id
        self.title = title
        self.generated_title = generated_title
        self.generated_summary = generated_summary
        self.summary = summary
        self.category = category

def update_digest_content():
    """更新数据库中ID为38的快报内容"""
    
    # 获取数据库文件路径
    db_path = os.environ.get("DATABASE_URL", "daily_digest.db")
    
    # 如果数据库路径是SQLAlchemy URL，则提取文件路径
    if db_path.startswith("sqlite:///"):
        db_path = db_path[10:]  # 移除 "sqlite:///" 前缀
    
    print(f"使用数据库路径: {db_path}")
    
    # 确保数据库存在
    if not Path(db_path).exists():
        print(f"数据库文件不存在: {db_path}")
        return False
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询ID为38的快报及其关联的新闻
        digest_id = 38
        cursor.execute("""
            SELECT n.id, n.title, n.generated_title, n.generated_summary, n.summary, n.category
            FROM news n
            JOIN digest_news dn ON n.id = dn.news_id
            WHERE dn.digest_id = ?
        """, (digest_id,))
        
        news_items = cursor.fetchall()
        
        print(f"=== 更新快报 ID: {digest_id} ===")
        print(f"关联的新闻数量: {len(news_items)}")
        
        if not news_items:
            print("没有找到关联的新闻")
            return False
        
        # 创建MockNews对象
        mock_news_items = []
        for news in news_items:
            news_id, title, generated_title, generated_summary, summary, category = news
            
            # 导入NewsCategory枚举
            from app.models.news import NewsCategory
            category_enum = getattr(NewsCategory, category, NewsCategory.OTHER)
            
            mock_news = MockNews(
                id=news_id,
                title=title,
                generated_title=generated_title,
                generated_summary=generated_summary,
                summary=summary,
                category=category_enum
            )
            mock_news_items.append(mock_news)
        
        # 使用修复后的函数生成新的快报内容
        print(f"正在生成修复后的快报内容...")
        fixed_content = create_digest_content(mock_news_items)
        
        # 查询当前快报内容
        cursor.execute("SELECT content FROM digests WHERE id = ?", (digest_id,))
        old_content = cursor.fetchone()[0]
        
        print(f"原内容长度: {len(old_content)} 字符")
        print(f"新内容长度: {len(fixed_content)} 字符")
        
        # 检查是否有改变
        if old_content == fixed_content:
            print("内容没有变化，无需更新")
            return True
        
        # 更新快报内容
        cursor.execute("""
            UPDATE digests 
            SET content = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (fixed_content, digest_id))
        
        # 清除PDF路径，因为内容已更改
        cursor.execute("""
            UPDATE digests 
            SET pdf_path = NULL
            WHERE id = ?
        """, (digest_id,))
        
        # 提交更改
        conn.commit()
        
        print(f"快报内容已成功更新！")
        print(f"PDF路径已清除，下次下载时将重新生成")
        
        # 验证更新
        cursor.execute("SELECT content FROM digests WHERE id = ?", (digest_id,))
        updated_content = cursor.fetchone()[0]
        
        if "    - \n" in updated_content:
            print("*** 警告: 更新后仍有空摘要行 ***")
        else:
            print("*** 确认: 更新后没有空摘要行 ***")
        
        # 关闭连接
        conn.close()
        return True
        
    except Exception as e:
        print(f"更新过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    update_digest_content() 