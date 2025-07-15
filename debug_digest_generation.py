import os
import sqlite3
from pathlib import Path
from datetime import datetime

def test_digest_generation():
    """测试快报生成过程，找出空摘要行的原因"""
    
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
        
        print(f"=== 测试ID为{digest_id}的快报生成 ===")
        print(f"关联的新闻数量: {len(news_items)}")
        
        if not news_items:
            print("没有找到关联的新闻")
            return False
        
        # 模拟快报生成过程
        print("\n=== 模拟快报生成过程 ===")
        
        # 按分类对新闻进行分组
        categorized_news = {}
        for news in news_items:
            news_id, title, generated_title, generated_summary, summary, category = news
            
            print(f"\n处理新闻 ID: {news_id}")
            print(f"  原标题: {title}")
            print(f"  生成标题: {generated_title}")
            print(f"  生成摘要: {repr(generated_summary)}")
            print(f"  原摘要: {repr(summary)}")
            print(f"  分类: {category}")
            
            # 选择标题和摘要
            final_title = generated_title or title
            final_summary = generated_summary or summary
            
            print(f"  最终标题: {final_title}")
            print(f"  最终摘要: {repr(final_summary)}")
            
            # 检查摘要问题
            if not final_summary:
                print(f"  *** 警告: 最终摘要为空或None ***")
            elif final_summary.strip() == "":
                print(f"  *** 警告: 最终摘要只有空白字符 ***")
            
            # 按分类分组
            if category not in categorized_news:
                categorized_news[category] = []
            categorized_news[category].append({
                'title': final_title,
                'summary': final_summary,
                'id': news_id
            })
        
        print(f"\n=== 按分类分组结果 ===")
        for category, items in categorized_news.items():
            print(f"分类 {category}: {len(items)} 条新闻")
        
        # 生成Markdown内容
        print(f"\n=== 生成Markdown内容 ===")
        today = datetime.now().strftime('%Y%m%d')
        md_content = f"# **每日网安情报速递【{today}】**\n\n------\n\n"
        
        # 定义分类顺序
        category_order = ["FINANCIAL", "MAJOR", "DATA_LEAK", "VULNERABILITY"]
        category_names = {
            "FINANCIAL": "一、金融业网络安全事件",
            "MAJOR": "二、重大网络安全事件", 
            "DATA_LEAK": "三、重大数据泄露事件",
            "VULNERABILITY": "四、重大漏洞风险提示"
        }
        
        for category in category_order:
            category_name = category_names.get(category, f"、{category}")
            md_content += f"### {category_name}\n\n"
            
            # 检查是否有该分类的新闻
            if category in categorized_news and categorized_news[category]:
                news_in_category = categorized_news[category]
                print(f"\n处理分类 {category_name}: {len(news_in_category)} 条新闻")
                
                for i, news in enumerate(news_in_category, 1):
                    title = news['title']
                    summary = news['summary']
                    
                    print(f"  新闻 {i}: {title}")
                    print(f"    摘要: {repr(summary)}")
                    
                    md_content += f"{i}. **{title}**\n"
                    md_content += f"    - {summary}\n"
                    
                    # 检查是否产生了空摘要行
                    if not summary:
                        print(f"    *** 发现空摘要！将产生 '    - ' 行 ***")
                    
                    if i < len(news_in_category):  # 不是最后一条新闻时添加空行
                        md_content += "\n"
            else:
                # 没有该分类的新闻时显示"暂无"
                md_content += "> 暂无\n"
                print(f"\n分类 {category_name}: 没有新闻，显示'暂无'")
            
            md_content += "\n------\n\n"
        
        print(f"\n=== 最终生成的Markdown内容 ===")
        print(repr(md_content))
        
        # 检查是否包含空摘要行
        if "    - \n" in md_content:
            print(f"\n*** 发现空摘要行！这是问题所在 ***")
            lines = md_content.split('\n')
            for i, line in enumerate(lines):
                if line == "    - ":
                    print(f"第 {i+1} 行: {repr(line)}")
        
        # 关闭连接
        conn.close()
        return True
        
    except Exception as e:
        print(f"调试过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_digest_generation() 