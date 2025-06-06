import os
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from app.models.news import NewsCategory

# 获取日志记录器
from app.config import get_logger
logger = get_logger(__name__)

# 尝试导入WeasyPrint，如果失败则提供替代方案
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
    logger.info("WeasyPrint已成功加载")
except (ImportError, OSError) as e:
    WEASYPRINT_AVAILABLE = False
    logger.warning(f"WeasyPrint加载失败: {str(e)}")
    logger.warning("PDF生成功能将不可用。请按照以下链接安装必要的依赖：")
    logger.warning("https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation")
    logger.warning("Windows平台需要安装GTK+3: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases")

# 加载模板引擎
template_env = Environment(loader=FileSystemLoader("app/templates"))

def get_category_name(category):
    """获取分类的中文名称"""
    category_names = {
        NewsCategory.FINANCIAL: "金融业网络安全事件",
        NewsCategory.MAJOR: "重大网络安全事件",
        NewsCategory.DATA_LEAK: "重大数据泄露事件",
        NewsCategory.VULNERABILITY: "重大漏洞风险提示",
        NewsCategory.OTHER: "其他"
    }
    return category_names.get(category, "其他")

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
        NewsCategory.VULNERABILITY,
        NewsCategory.OTHER
    ]
    
    for category in category_order:
        if category not in categorized_news:
            continue
            
        news_in_category = categorized_news[category]
        if not news_in_category:
            continue
            
        category_name = get_category_name(category)
        md_content += f"### {category_name}\n\n"
        
        for i, news in enumerate(news_in_category, 1):
            title = news.generated_title or news.title
            summary = news.generated_summary or news.summary
            
            md_content += f"{i}. **{title}**\n"
            md_content += f"   - {summary}\n"
        
        md_content += "\n------\n\n"
    
    return md_content

def generate_pdf(digest):
    """生成PDF文件"""
    # 如果WeasyPrint不可用，返回None并记录警告
    if not WEASYPRINT_AVAILABLE:
        logger.warning("无法生成PDF：WeasyPrint不可用")
        return None
    
    # 创建存储PDF的目录
    pdf_dir = "app/static/pdf"
    os.makedirs(pdf_dir, exist_ok=True)
    
    # 设置文件名
    file_name = f"digest_{digest.date.strftime('%Y%m%d')}_{digest.id}.pdf"
    pdf_path = os.path.join(pdf_dir, file_name)
    
    try:
        # 渲染HTML模板
        template = template_env.get_template("pdf_template.html")
        
        # 将content转为HTML（使用markdown库）
        import markdown
        html_content = markdown.markdown(digest.content)
        
        # 渲染模板
        html = template.render(
            title=digest.title,
            date=digest.date.strftime('%Y-%m-%d'),
            content=html_content
        )
        
        # 生成PDF
        HTML(string=html).write_pdf(pdf_path)
        
        # 返回相对路径（用于存储和访问）
        rel_path = os.path.join("static", "pdf", file_name)
        logger.info(f"PDF已生成: {rel_path}")
        
        return rel_path
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