import os
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from app.models.news import NewsCategory

# 获取日志记录器
from app.config import get_logger
logger = get_logger(__name__)

# 导入Playwright PDF生成器
try:
    from app.services.playwright_pdf_generator import generate_pdf as generate_pdf_playwright
    PLAYWRIGHT_AVAILABLE = True
    logger.info("Playwright PDF生成器已成功加载")
except (ImportError, OSError) as e:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning(f"Playwright PDF生成器加载失败: {str(e)}")
    logger.warning("PDF生成功能将不可用。请安装playwright: pip install playwright && playwright install chromium")

# 加载模板引擎
template_env = Environment(loader=FileSystemLoader("app/templates"))

def get_category_name(category, index):
    """获取分类的中文名称（带序号）"""
    category_names = {
        NewsCategory.FINANCIAL: "一、金融业网络安全事件",
        NewsCategory.MAJOR: "二、重大网络安全事件", 
        NewsCategory.DATA_LEAK: "三、重大数据泄露事件",
        NewsCategory.VULNERABILITY: "四、重大漏洞风险提示"
    }
    return category_names.get(category, f"{index}、其他")

def create_digest_content(news_items):
    """创建快报内容（Markdown格式）"""
    # 按分类对新闻进行分组
    categorized_news = {}
    for news in news_items:
        category = news.category or NewsCategory.OTHER
        if category not in categorized_news:
            categorized_news[category] = []
        categorized_news[category].append(news)
    
    # 生成Markdown内容
    today = datetime.now().strftime('%Y%m%d')
    
    md_content = f"# **每日网安情报速递【{today}】**\n\n------\n\n"
    
    # 按特定顺序处理分类
    category_order = [
        NewsCategory.FINANCIAL,
        NewsCategory.MAJOR,
        NewsCategory.DATA_LEAK,
        NewsCategory.VULNERABILITY
    ]
    
    for category in category_order:
        category_name = get_category_name(category, category_order.index(category) + 1)
        md_content += f"### {category_name}\n\n"
        
        # 检查是否有该分类的新闻
        if category in categorized_news and categorized_news[category]:
            news_in_category = categorized_news[category]
            
            for i, news in enumerate(news_in_category, 1):
                title = news.generated_title or news.title
                summary = news.generated_summary or news.summary
                
                # 清理摘要：去除开头和结尾的换行符和空白字符
                if summary:
                    summary = summary.strip()
                    
                # 如果摘要为空或只有空白字符，使用备用文本
                if not summary:
                    summary = "暂无摘要"
                
                md_content += f"{i}. **{title}**\n"
                md_content += f"    - {summary}\n"
                if i < len(news_in_category):  # 不是最后一条新闻时添加空行
                    md_content += "\n"
        else:
            # 没有该分类的新闻时显示"暂无"
            md_content += "> 暂无\n"
        
        md_content += "\n------\n\n"
    
    # 处理"其他"分类（只有在有新闻条目时才显示）
    if NewsCategory.OTHER in categorized_news and categorized_news[NewsCategory.OTHER]:
        md_content += f"### 五、其他\n\n"
        
        other_news = categorized_news[NewsCategory.OTHER]
        for i, news in enumerate(other_news, 1):
            title = news.generated_title or news.title
            summary = news.generated_summary or news.summary
            
            # 清理摘要：去除开头和结尾的换行符和空白字符
            if summary:
                summary = summary.strip()
                
            # 如果摘要为空或只有空白字符，使用备用文本
            if not summary:
                summary = "暂无摘要"
            
            md_content += f"{i}. **{title}**\n"
            md_content += f"    - {summary}\n"
            if i < len(other_news):  # 不是最后一条新闻时添加空行
                md_content += "\n"
        
        md_content += "\n------\n\n"
    
    return md_content

def generate_pdf(digest):
    """生成PDF文件"""
    # 如果Playwright不可用，返回None并记录警告
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("无法生成PDF：Playwright不可用")
        return None
    
    try:
        # 使用Playwright生成PDF
        pdf_path = generate_pdf_playwright(digest)
        
        if pdf_path:
            logger.info(f"PDF已生成: {pdf_path}")
            return pdf_path
        else:
            logger.error("PDF生成失败")
            return None
            
    except Exception as e:
        logger.error(f"生成PDF失败: {str(e)}")
        return None

def find_similar_news(news_item, all_news, threshold=0.7):
    """使用NLP找到相似的新闻"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np
    
    # 如果只有一个新闻，无需比较
    if len(all_news) <= 1:
        return []
    
    # 提取文本内容
    texts = [n.content for n in all_news]
    
    # 计算TF-IDF特征
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(texts)
    
    # 当前新闻的索引
    idx = all_news.index(news_item)
    
    # 计算余弦相似度
    from sklearn.metrics.pairwise import cosine_similarity
    cosine_similarities = cosine_similarity(tfidf_matrix[idx:idx+1], tfidf_matrix).flatten()
    
    # 找到相似度高于阈值的新闻（排除自身）
    similar_indices = np.where(cosine_similarities > threshold)[0]
    similar_indices = [i for i in similar_indices if i != idx]
    
    # 返回相似的新闻
    return [all_news[i] for i in similar_indices]

def deduplicate_news(news_items):
    """去除重复的新闻"""
    # 已处理过的新闻ID集合
    processed_ids = set()
    unique_news = []
    
    for news in news_items:
        if news.id in processed_ids:
            continue
            
        # 添加到结果和已处理集合
        unique_news.append(news)
        processed_ids.add(news.id)
        
        # 找相似的新闻并标记为已处理
        similar_news = find_similar_news(news, news_items)
        for similar in similar_news:
            processed_ids.add(similar.id)
    
    return unique_news 