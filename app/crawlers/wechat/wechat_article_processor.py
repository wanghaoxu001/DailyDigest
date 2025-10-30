import os
import json
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Type

# 导入爬虫和解析器模块
from .playwright_wechat_crawler import WechatArticleCrawler
from ..parsers import BaseArticleParser
from ..parsers.security_digest_parser import SecurityDigestParser


class ArticleParserRegistry:
    """文章解析器注册表，根据文章标题选择合适的解析器"""

    def __init__(self):
        self.parsers = {}  # 存储标题模式到解析器的映射

    def register(self, title_pattern: str, parser_class: Type[BaseArticleParser]):
        """注册解析器

        Args:
            title_pattern: 标题匹配模式（正则表达式）
            parser_class: 解析器类
        """
        self.parsers[title_pattern] = parser_class

    def get_parser(self, title: str) -> Optional[Type[BaseArticleParser]]:
        """根据文章标题获取合适的解析器

        Args:
            title: 文章标题

        Returns:
            解析器类或None（如果没有匹配的解析器）
        """
        for pattern, parser_class in self.parsers.items():
            if re.search(pattern, title, re.IGNORECASE):
                return parser_class
        return None


# 全局解析器注册表
parser_registry = ArticleParserRegistry()

# 注册默认解析器
parser_registry.register(r"^5th域安全微讯早报", SecurityDigestParser)


class WechatArticleProcessor:
    """微信文章处理器"""

    def __init__(self, output_dir: str = "data/processed_articles"):
        """初始化处理器

        Args:
            output_dir: 处理结果输出目录
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 初始化爬虫
        self.crawler = WechatArticleCrawler(
            headless=True, image_enabled=True, timeout=60000, retry_times=2
        )

    async def process_url(self, url: str, rss_entry: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """处理单个URL

        Args:
            url: 微信文章URL
            rss_entry: RSS条目对象（可选），如果提供且包含足够内容，将跳过爬虫直接使用

        Returns:
            Dict: 处理结果，或None（如果处理失败）
        """
        article_data = None
        
        # 1. 检查RSS条目是否已包含足够的内容
        if rss_entry:
            rss_content_html = ""
            if hasattr(rss_entry, "content") and rss_entry.content:
                if isinstance(rss_entry.content, list) and len(rss_entry.content) > 0:
                    rss_content_html = rss_entry.content[0].get("value", "")
            
            if len(rss_content_html) > 100:
                print(f"RSS内容足够长 ({len(rss_content_html)} 字符)，跳过Playwright爬虫，直接使用RSS内容")
                
                # 从RSS entry.title提取元数据
                title = getattr(rss_entry, "title", "")
                
                # 解析标题中的日期和期号（针对5th域安全微讯早报等格式）
                title_match = re.search(r"(.*?)【(\d+)】(\d+)期", title)
                digest_date = ""
                issue_number = ""
                if title_match:
                    digest_date = title_match.group(2)
                    issue_number = title_match.group(3)
                    print(f"  提取元数据 - 日期: {digest_date}, 期号: {issue_number}")
                
                # 构造模拟的article_data，跳过爬虫
                article_data = {
                    "success": True,
                    "title": title,
                    "content": rss_content_html,
                    "crawl_time": datetime.now().isoformat(),
                    "source": "rss_content",  # 标记来源
                    "digest_date": digest_date,  # 新增：从标题提取的日期
                    "issue_number": issue_number,  # 新增：从标题提取的期号
                }
        
        # 2. 如果RSS内容不足或未提供，使用爬虫抓取
        if not article_data:
            print(f"使用Playwright爬虫抓取文章: {url}")
            article_data = await self.crawler.crawl_article(url)

        if not article_data or not article_data.get("success", False):
            print(f"爬取文章失败: {url}")
            return None

        # 3. 解析文章内容
        title = article_data.get("title", "")
        content = article_data.get("content", "")

        if not title or not content:
            print(f"文章标题或内容为空: {url}")
            return None

        print(f"成功爬取文章: {title}")

        # 3. 根据标题选择解析器
        parser_class = parser_registry.get_parser(title)

        if not parser_class:
            print(f"未找到适用于标题 '{title}' 的解析器")
            # 保存原始内容，以便后续手动处理
            self._save_raw_article(article_data, "no_parser")
            return article_data

        # 4. 使用解析器处理内容
        try:
            # 准备元数据（从article_data中提取）
            metadata = {
                "title": title,
                "date": article_data.get("digest_date", ""),
                "issue_number": article_data.get("issue_number", ""),
            }
            
            # 创建解析器实例，传入元数据
            parser = parser_class(content, metadata=metadata)
            parsed_data = parser.parse()

            # 5. 添加元数据
            parsed_data["source_url"] = url
            parsed_data["original_title"] = title
            parsed_data["crawl_time"] = article_data.get(
                "crawl_time", datetime.now().isoformat()
            )

            # 6. 保存结果
            result = self._save_parsed_article(parsed_data)
            
            # 7. 将article_data中的重要字段添加到result中
            result["source"] = article_data.get("source", "crawler")
            result["digest_date"] = article_data.get("digest_date", "")
            result["issue_number"] = article_data.get("issue_number", "")
            result["content"] = article_data.get("content", "")
            
            print(f"result: {result}")
            print(result)
            print("=" * 50)
            print(f"raw_content: {article_data.get('content', '')[:500]}...")
            print("=" * 50)
            print(f"成功解析文章: {title}")
            return result
        except Exception as e:
            print(f"解析文章时出错: {str(e)}")
            # 保存原始内容，以便后续手动处理
            self._save_raw_article(article_data, "parse_error")
            return article_data

    def _save_raw_article(self, article_data: Dict[str, Any], reason: str) -> str:
        """保存原始文章数据

        Args:
            article_data: 爬取的原始文章数据
            reason: 保存原因（no_parser或parse_error）

        Returns:
            str: 保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title_slug = self._slugify(article_data.get("title", "untitled"))
        filename = f"{timestamp}_{title_slug}_{reason}.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2)

        print(f"原始文章已保存到: {filepath}")
        return filepath

    def _save_parsed_article(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存解析后的文章数据

        Args:
            parsed_data: 解析后的文章数据

        Returns:
            Dict: 包含保存信息的结果
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = parsed_data.get("title", "")
        title_slug = self._slugify(title)

        # 生成文件名
        if "issue_number" in parsed_data:
            filename = f"{timestamp}_{title_slug}_{parsed_data['issue_number']}.json"
        else:
            filename = f"{timestamp}_{title_slug}.json"

        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, ensure_ascii=False, indent=2)

        print(f"解析结果已保存到: {filepath}")

        # 返回结果
        return {
            "title": title,
            "url": parsed_data.get("source_url", ""),
            "output_file": filepath,
            "timestamp": timestamp,
            "parsed_data": parsed_data,
        }

    def _slugify(self, text: str) -> str:
        """将文本转换为URL友好的格式

        Args:
            text: 原始文本

        Returns:
            str: URL友好的文本
        """
        # 移除非字母数字字符
        text = re.sub(r"[^\w\s-]", "", text)
        # 将空格替换为下划线
        text = re.sub(r"\s+", "_", text)
        # 限制长度
        return text[:50]


async def process_url(url: str, rss_entry: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """便捷函数，处理单个URL

    Args:
        url: 微信文章URL
        rss_entry: RSS条目对象（可选），如果提供且包含足够内容，将跳过爬虫直接使用

    Returns:
        Dict: 处理结果，或None（如果处理失败）
    """
    processor = WechatArticleProcessor()
    return await processor.process_url(url, rss_entry=rss_entry)


async def main():
    """主函数，用于测试"""
    # 测试URL
    url = "https://mp.weixin.qq.com/s/cd_f18TysikG7dXN8TqMIQ"

    print(f"开始处理文章: {url}")
    result = await process_url(url)

    if result and "parsed_data" in result:
        parsed_data = result["parsed_data"]
        print(f"\n处理结果:")
        print(f"- 标题: {parsed_data.get('title', '')}")
        print(f"- 期号: {parsed_data.get('issue_number', '')}")

        news_count = parsed_data.get("news_count", 0)
        print(f"- 新闻数量: {news_count}")

        categories = parsed_data.get("categories", {})
        for category, news_list in categories.items():
            if news_list:
                print(f"  - {category}: {len(news_list)} 条")
    else:
        print("文章处理失败或未能解析")


if __name__ == "__main__":
    asyncio.run(main())
