import feedparser
import requests
import newspaper
from newspaper import Article
from bs4 import BeautifulSoup
import logging
import uuid
from datetime import datetime, timedelta
import time
from sqlalchemy.orm import Session
import html2text
import io
import threading
import traceback
import os
import nltk
import random  # 添加random模块导入
import re
import asyncio
from typing import Any, Optional, Dict, List, Tuple
from collections import deque
import html # Added for HTML entity unescaping
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.db.session import SessionLocal
from app.models.source import Source, SourceType
from app.models.news import News
from app.models.task_execution import TaskExecution
from app.services.llm_processor import process_news

# 导入微信文章爬虫和处理器
from app.crawlers.wechat.playwright_wechat_crawler import WechatArticleCrawler
from app.crawlers.parsers.security_digest_parser import SecurityDigestParser
from app.crawlers.wechat.wechat_article_processor import ArticleParserRegistry, process_url as process_wechat_url_external

# 获取日志记录器
from app.config import get_logger
logger = get_logger(__name__)

# HTML转文本工具
html_converter = html2text.HTML2Text()
html_converter.ignore_links = False
html_converter.ignore_images = True

# 创建专门用于清理HTML标记的转换器
html_cleaner = html2text.HTML2Text()
html_cleaner.ignore_links = True
html_cleaner.ignore_images = True
html_cleaner.ignore_emphasis = True
html_cleaner.ignore_tables = True
html_cleaner.unicode_snob = True
html_cleaner.body_width = 0  # 不进行换行
html_cleaner.use_automatic_links = False


def clean_html_content(content: str) -> str:
    """
    清理HTML标记和Markdown文本标记，返回纯文本内容
    """
    if not content:
        return content
    
    try:
        # 使用html2text清理HTML标记
        cleaned = html_cleaner.handle(content)
        
        # 移除残留的特殊字符
        cleaned = re.sub(r'&#\d+;', '', cleaned)  # 移除HTML实体编码
        cleaned = re.sub(r'&[a-zA-Z]+;', '', cleaned)  # 移除HTML实体名称
        
        # 移除Markdown格式标记（在清理换行之前处理）
        # 移除标题标记 #
        cleaned = re.sub(r'^\s*#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
        
        # 移除引用标记 > 
        cleaned = re.sub(r'^\s*>\s*', '', cleaned, flags=re.MULTILINE)
        
        # 移除列表标记 - 或 * 或 数字.
        cleaned = re.sub(r'^\s*[-\*\+]\s+', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^\s*\d+\.\s+', '', cleaned, flags=re.MULTILINE)
        
        # 移除图片标记 ![alt](url) -> alt (必须在链接标记之前处理)
        cleaned = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', cleaned)
        
        # 移除链接标记 [text](url) -> text
        cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)
        
        # 移除粗体标记 **text** 或 __text__
        cleaned = re.sub(r'\*\*([^\*]+)\*\*', r'\1', cleaned)
        cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
        
        # 移除斜体标记 *text* 或 _text_ (注意避免与粗体标记冲突)
        cleaned = re.sub(r'(?<!\*)\*(?!\*)([^\*]+)\*(?!\*)', r'\1', cleaned)
        cleaned = re.sub(r'(?<!_)_(?!_)([^_]+)_(?!_)', r'\1', cleaned)
        
        # 移除删除线 ~~text~~
        cleaned = re.sub(r'~~([^~]+)~~', r'\1', cleaned)
        
        # 移除行内代码标记 `text`
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
        
        # 清理多余的换行符和空格
        cleaned = re.sub(r'\n\s*\n', '\n', cleaned)  # 移除多余的空行
        cleaned = re.sub(r'\n+', ' ', cleaned)  # 将换行转换为空格
        cleaned = re.sub(r'\s+', ' ', cleaned)  # 合并多个空格
        cleaned = cleaned.strip()
        
        return cleaned
    except Exception as e:
        logger.warning(f"清理HTML内容失败: {str(e)}", exc_info=True)
        # 如果清理失败，至少尝试移除基本的HTML标签
        return re.sub(r'<[^>]+>', '', content)

# 使用全局日志管理器
from app.config import log_manager

# 常用浏览器请求头（用于绕过基础反爬/Cloudflare页）
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _create_http_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
# ================== 源级日志缓冲（内存） ==================
# 为每个源维护独立环形缓冲，便于前端精准查看该源日志
_SOURCE_LOGS: Dict[int, deque[str]] = {}
_SOURCE_LOGS_LOCK = threading.Lock()
_SOURCE_LOGS_MAX_LINES = 1000

def _append_source_log(source_id: int, message: str) -> None:
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} - {message}"
        with _SOURCE_LOGS_LOCK:
            if source_id not in _SOURCE_LOGS:
                _SOURCE_LOGS[source_id] = deque(maxlen=_SOURCE_LOGS_MAX_LINES)
            _SOURCE_LOGS[source_id].append(line)
    except Exception:
        pass

def get_source_logs(source_id: int, max_lines: int = 1000) -> List[str]:
    with _SOURCE_LOGS_LOCK:
        if source_id not in _SOURCE_LOGS:
            return []
        logs = list(_SOURCE_LOGS[source_id])
        return logs[-max_lines:] if max_lines and max_lines > 0 else logs

def clear_source_logs(source_id: int) -> None:
    with _SOURCE_LOGS_LOCK:
        _SOURCE_LOGS[source_id] = deque(maxlen=_SOURCE_LOGS_MAX_LINES)

# 确保NLTK资源文件已下载
try:
    nltk.data.find("tokenizers/punkt")
    logger.info("NLTK punkt资源已存在")
except LookupError:
    logger.info("正在下载NLTK punkt资源...")
    nltk.download("punkt")  # type: ignore
    logger.info("NLTK punkt资源下载完成")
try:
    nltk.data.find("tokenizers/punkt_tab")  # type: ignore
except LookupError:
    logger.info("正在下载punkt_tab资源...")
    nltk.download("punkt_tab")  # type: ignore
    logger.info("punkt_tab资源下载完成")


async def _get_content_with_newspaper4k(
    article_url: str,
    article_title: str,  # Default title, can be overridden by newspaper
    fallback_feed_entry: Optional[feedparser.FeedParserDict] = None,
    existing_article_obj: Optional[Article] = None,
) -> Dict[str, Any]:
    """
    Helper function to fetch and parse an article using Newspaper4k,
    with fallbacks for content, summary, and publish date.
    Returns a dictionary with 'parsed_title', 'content', 'summary', 'publish_date', 'keywords'.
    """
    logger.info(
        f"Newspaper4k: Processing URL: {article_url} (Title hint: {article_title[:30]})"
    )

    text_content = ""
    summary = ""
    publish_date = datetime.now()
    keywords: List[str] = []
    parsed_title = article_title  # Use provided title as default

    # Try to get initial summary and publish date from fallback_feed_entry if available
    if fallback_feed_entry:
        if hasattr(fallback_feed_entry, "summary") and fallback_feed_entry.summary:
            summary = fallback_feed_entry.summary
        if (
            hasattr(fallback_feed_entry, "published_parsed")
            and fallback_feed_entry.published_parsed
        ):
            try:
                publish_date = datetime.fromtimestamp(
                    time.mktime(fallback_feed_entry.published_parsed)
                )
            except (TypeError, ValueError, OverflowError) as e_date:
                logger.warning(
                    f"Newspaper4k: RSS entry date parsing failed for {article_url}: {str(e_date)}"
                )

    try:
        article_obj = (
            existing_article_obj if existing_article_obj else Article(article_url)
        )
        if not existing_article_obj:  # If it's a new article object from URL
            article_obj.download()
        article_obj.parse()

        parsed_title = article_obj.title if article_obj.title else article_title
        text_content = article_obj.text

        if text_content and len(text_content) > 1000:
            try:
                article_obj.nlp()
                if (
                    article_obj.summary
                ):  # Prefer newspaper's summary if available and NLP ran
                    summary = article_obj.summary
            except Exception as e_nlp:
                logger.warning(
                    f"Newspaper4k: NLP keyword/summary extraction failed for {article_url}: {str(e_nlp)}"
                )
                if not summary and text_content:  # Fallback summary from content
                    summary = text_content[:500] + "..."
        elif (
            text_content and not summary
        ):  # Content not None but too short for NLP, or NLP failed and no prior summary
            summary = text_content[:500] + "..."

        if article_obj.publish_date:  # Prefer newspaper's publish date
            publish_date = article_obj.publish_date

        # If Newspaper4k extracted little or no content, try fallback from feed entry
        if (not text_content or len(text_content) < 100) and fallback_feed_entry:
            logger.warning(
                f"Newspaper4k: Content short/missing for {article_url}. Trying fallback feed entry content."
            )
            entry_content_html = ""
            if (
                hasattr(fallback_feed_entry, "content")
                and fallback_feed_entry.content
                and isinstance(fallback_feed_entry.content, list)
                and fallback_feed_entry.content[0].get("value")
            ):
                entry_content_html = fallback_feed_entry.content[0].get("value", "")
            elif (
                hasattr(fallback_feed_entry, "summary") and fallback_feed_entry.summary
            ):  # Use summary if content not available
                entry_content_html = fallback_feed_entry.summary
            elif (
                hasattr(fallback_feed_entry, "description")
                and fallback_feed_entry.description
            ):
                entry_content_html = fallback_feed_entry.description

            if entry_content_html:
                try:
                    text_content = html_converter.handle(entry_content_html)
                    if (
                        not summary and text_content
                    ):  # If summary was still empty, derive from this new content
                        summary = text_content[:500] + "..."
                except Exception as e_html:
                    logger.warning(
                        f"Newspaper4k: Fallback HTML conversion failed for {article_url}: {str(e_html)}"
                    )

        if not text_content:
            logger.warning(
                f"Newspaper4k: Could not retrieve content for {article_url} from Newspaper4k or fallback."
            )
            # Return empty/default values but log it happened
            return {
                "parsed_title": parsed_title,
                "content": "",
                "summary": summary or "摘要不可用",
                "publish_date": publish_date,
                "keywords": [],
                "original_url": article_url,
            }

    except Exception as e_np:
        logger.warning(
            f"Newspaper4k: Main processing failed for {article_url}: {str(e_np)}. Using fallbacks."
        )
        # Fallback to RSS entry content directly if Newspaper4k fails catastrophically
        if fallback_feed_entry:
            entry_content_html = ""
            if (
                hasattr(fallback_feed_entry, "content")
                and fallback_feed_entry.content
                and isinstance(fallback_feed_entry.content, list)
                and fallback_feed_entry.content[0].get("value")
            ):
                entry_content_html = fallback_feed_entry.content[0].get("value", "")
            elif (
                hasattr(fallback_feed_entry, "summary") and fallback_feed_entry.summary
            ):
                entry_content_html = fallback_feed_entry.summary
            elif (
                hasattr(fallback_feed_entry, "description")
                and fallback_feed_entry.description
            ):
                entry_content_html = fallback_feed_entry.description

            if entry_content_html:
                try:
                    text_content = html_converter.handle(entry_content_html)
                except Exception as e_conv_fallback:
                    logger.warning(
                        f"Newspaper4k: Fallback HTML conversion failed (after NP error) for {article_url}: {str(e_conv_fallback)}"
                    )
                    text_content = entry_content_html  # Keep HTML as last resort

            # Ensure summary if not set and content exists
            if not summary and text_content:
                summary = text_content[:500] + "..."
            elif (
                not summary
                and hasattr(fallback_feed_entry, "summary")
                and fallback_feed_entry.summary
            ):
                summary = fallback_feed_entry.summary

            # Date handling (repeated for clarity in fallback)
            if (
                hasattr(fallback_feed_entry, "published_parsed")
                and fallback_feed_entry.published_parsed
            ):
                try:
                    publish_date = datetime.fromtimestamp(
                        time.mktime(fallback_feed_entry.published_parsed)
                    )
                except (TypeError, ValueError, OverflowError) as e_date_fallback:
                    logger.warning(
                        f"Newspaper4k: RSS date parsing failed (fallback) for {article_url}: {str(e_date_fallback)}"
                    )

        if not text_content:
            logger.error(
                f"Newspaper4k: All attempts failed for {article_url}. No content."
            )
            return {
                "parsed_title": parsed_title,
                "content": "",
                "summary": summary or "摘要不可用",
                "publish_date": publish_date,
                "keywords": [],
                "original_url": article_url,
            }

    # Final summary check
    if not summary and text_content:
        summary = text_content[:500] + "..."
    elif not summary and not text_content:
        summary = "摘要不可用"
        text_content = (
            "内容不可用"  # Should be caught by earlier returns if content is empty
        )

    return {
        "parsed_title": parsed_title,
        "content": clean_html_content(text_content),
        "summary": clean_html_content(summary),
        "publish_date": publish_date,
        "keywords": keywords,
        "original_url": article_url,
    }


async def get_standard_article_data(
    article_url: str,
    article_title: str,  # Initial title
    fallback_feed_entry: Optional[feedparser.FeedParserDict] = None,
    existing_article_obj: Optional[Article] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetches article data using Newspaper4k (via _get_content_with_newspaper4k).
    Returns a dictionary suitable for creating a News object, or None on failure.
    """
    logger.info(
        f"Standard Article Fetch: Attempting to get data for {article_url} (Title: {article_title[:30]})"
    )

    data = await _get_content_with_newspaper4k(
        article_url, article_title, fallback_feed_entry, existing_article_obj
    )

    if (
        not data["content"] and not data["summary"]
    ):  # Check if fetching was truly unsuccessful
        logger.warning(
            f"Standard Article Fetch: No content or summary for {article_url}. Skipping."
        )
        return None

    return {
        "title": article_title,
        "summary": data["summary"],
        "content": data["content"],
        "original_url": data["original_url"],
        "publish_date": data["publish_date"],
        "newspaper_keywords": data["keywords"],
        "entities": {},  # Placeholder, can be populated by caller if needed
        "is_processed": False,
    }


async def get_rss_entry_article_data(
    feed_entry: feedparser.FeedParserDict,
    use_newspaper: bool = True,
    use_description_as_summary: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Processes a single non-WeChat RSS feed entry using get_standard_article_data.
    Args:
        feed_entry: The RSS feed entry to process
        use_newspaper: Whether to use Newspaper4k to fetch article content. If False, only use RSS entry content.
        use_description_as_summary: When True, use 'description' field as fallback summary if no high-quality summary exists.
    """
    if (
        not hasattr(feed_entry, "link")
        or not feed_entry.link
        or not hasattr(feed_entry, "title")
        or not feed_entry.title
    ):
        logger.warning(
            f"RSS Entry Fetch: Skipping entry (missing link or title): {getattr(feed_entry, 'link', 'N/A')}"
        )
        return None

    logger.info(
        f"RSS Entry Fetch: Processing '{feed_entry.title[:30]}' ({feed_entry.link})"
    )

    if not use_newspaper:
        # 直接使用RSS条目内容
        logger.info(
            f"RSS Entry Fetch: Using RSS entry content directly for {feed_entry.link}"
        )

        # 获取内容
        content = ""
        if hasattr(feed_entry, "content") and feed_entry.content:
            content = feed_entry.content[0].value
        elif hasattr(feed_entry, "summary") and feed_entry.summary:
            content = feed_entry.summary
        elif hasattr(feed_entry, "description") and feed_entry.description:
            content = feed_entry.description

        # 获取发布时间
        publish_date = datetime.now()
        if hasattr(feed_entry, "published_parsed") and feed_entry.published_parsed:
            try:
                publish_date = datetime.fromtimestamp(
                    time.mktime(feed_entry.published_parsed)
                )
            except (TypeError, ValueError, OverflowError) as e_date:
                logger.warning(
                    f"RSS Entry Fetch: Date parsing failed for {feed_entry.link}: {str(e_date)}"
                )

        # 生成摘要，考虑备选摘要选项
        summary = ""
        
        # 首先尝试使用高质量的摘要
        if hasattr(feed_entry, "summary") and feed_entry.summary:
            summary_candidate = feed_entry.summary.strip()
            # 检查摘要质量（不能太短，不能和标题完全相同）
            if len(summary_candidate) > 150 and summary_candidate != feed_entry.title:
                summary = summary_candidate
        
        # 如果没有高质量摘要且启用了备选摘要选项，使用description
        if not summary and use_description_as_summary:
            if hasattr(feed_entry, "description") and feed_entry.description:
                description_candidate = feed_entry.description.strip()
                if len(description_candidate) > 20 and description_candidate != feed_entry.title:
                    summary = description_candidate
                    logger.info(f"RSS Entry Fetch: Using description as fallback summary for {feed_entry.link}")
        
        # 最后的备选方案：从内容生成摘要
        if not summary and content:
            summary = content[:500] + "..." if len(content) > 300 else content

        return {
            "title": feed_entry.title,
            "summary": clean_html_content(summary),
            "content": clean_html_content(content),
            "original_url": feed_entry.link,
            "publish_date": publish_date,
            "newspaper_keywords": [],  # 不使用Newspaper4k，所以没有关键词
            "entities": {},  # 实体将在后续LLM处理中生成
            "is_processed": False,
        }

    # 使用Newspaper4k获取内容
    # 如果启用了备选摘要选项，需要先处理feed_entry以包含description作为备选
    modified_feed_entry = feed_entry
    if use_description_as_summary:
        # 检查是否需要使用description作为摘要
        current_summary = getattr(feed_entry, 'summary', '')
        if not current_summary or len(current_summary.strip()) <= 50 or current_summary.strip() == feed_entry.title:
            # 当前摘要质量不佳，检查是否有description可用
            if hasattr(feed_entry, "description") and feed_entry.description:
                description_candidate = feed_entry.description.strip()
                if len(description_candidate) > 20 and description_candidate != feed_entry.title:
                    # 创建一个修改过的feed_entry副本，将description设为summary
                    modified_feed_entry = feedparser.FeedParserDict(feed_entry)
                    modified_feed_entry.summary = description_candidate
                    logger.info(f"RSS Entry Fetch: Modified feed entry to use description as summary for {feed_entry.link}")
    
    return await get_standard_article_data(
        article_url=feed_entry.link,
        article_title=feed_entry.title,
        fallback_feed_entry=modified_feed_entry,
    )


async def get_wechat_article_data(
    wechat_url: str, original_rss_entry: Optional[feedparser.FeedParserDict] = None
) -> List[Dict[str, Any]]:
    """
    Fetches and processes a WeChat article.
    Tries specific WeChat parsers first. If they fail or don't apply,
    falls back to standard Newspaper4k processing for the main URL.
    Returns a list of dictionaries, each suitable for News object creation.
    """
    logger.info(f"WeChat Article Fetch: Processing URL: {wechat_url}")
    processed_articles_data: List[Dict[str, Any]] = []

    # processor_result can be:
    # 1. None (if crawling failed)
    # 2. A dict with "parsed_data" (if custom parser ran), where "parsed_data" contains "news_items"
    # 3. A dict with raw crawled data (if no custom parser matched)
    processor_result = await process_wechat_url_external(wechat_url, rss_entry=original_rss_entry)

    if not processor_result:
        logger.warning(
            f"WeChat Article Fetch: Crawling failed or empty result from process_wechat_url_external for {wechat_url}"
        )
        return []

    custom_parsed_output = processor_result.get("parsed_data")
    custom_parsed_items = None
    if isinstance(custom_parsed_output, dict):
        custom_parsed_items = custom_parsed_output.get("news_items")

    pub_date = datetime.now()
    crawl_time_str = (
        custom_parsed_output.get("crawl_time")
        if isinstance(custom_parsed_output, dict)
        else None
    )
    processor_crawl_time = (
        processor_result.get("crawl_time")
        if isinstance(processor_result, dict)
        else None
    )

    rss_pub_date_found = False
    if original_rss_entry and hasattr(original_rss_entry, "published_parsed") and original_rss_entry.published_parsed:
        try:
            pub_date = datetime.fromtimestamp(time.mktime(original_rss_entry.published_parsed))
            logger.info(f"WeChat Article Fetch: Using RSS published time: {pub_date}")
            rss_pub_date_found = True
        except (TypeError, ValueError, OverflowError) as e_date:
            logger.warning(f"WeChat Article Fetch: RSS date parsing failed for {wechat_url}: {str(e_date)}", exc_info=True)

    if not rss_pub_date_found and crawl_time_str:
        try:
            pub_date = datetime.fromisoformat(crawl_time_str)
            logger.info(f"WeChat Article Fetch: Using parser crawl_time: {pub_date}")
            rss_pub_date_found = True
        except ValueError:
            logger.warning(
                f"WeChat Article Fetch: Cannot parse crawl_time '{crawl_time_str}', using current time."
            )

    if not rss_pub_date_found and processor_crawl_time:
        try:
            pub_date = datetime.fromisoformat(processor_crawl_time)
            logger.info(f"WeChat Article Fetch: Using processor crawl_time: {pub_date}")
        except ValueError:
            logger.warning(
                f"WeChat Article Fetch: Cannot parse processor crawl_time '{processor_crawl_time}', using current time."
            )

    if (
        custom_parsed_items
        and isinstance(custom_parsed_items, list)
        and custom_parsed_items
    ):
        logger.info(
            f"WeChat Article Fetch: Specific parser yielded {len(custom_parsed_items)} items for {wechat_url}"
        )

        for item in custom_parsed_items:
            item_title = item.get("title", "无标题")
            content = item.get("content", "")
            summary = content[:500] + "..." if len(content) > 300 else content
            category = item.get("category", "")

            entities = {
                "wechat_article": True,
                "category": category,
                "parent_title": custom_parsed_output.get("title", ""),
                "issue_number": custom_parsed_output.get("issue_number", ""),
                "original_author": custom_parsed_output.get("author", ""),
            }
            processed_articles_data.append(
                {
                    "title": item_title,
                    "summary": clean_html_content(summary),
                    "content": clean_html_content(content),
                    "original_url": wechat_url,  # All sub-items share the parent URL
                    "publish_date": pub_date,
                    "newspaper_keywords": [],  # Specific parsers usually don't provide these
                    "entities": entities,
                    "is_processed": False,
                }
            )
        return processed_articles_data
    else:
        # 检查是否使用了RSS内容
        if processor_result and processor_result.get("source") == "rss_content":
            logger.info(
                f"WeChat Article Fetch: Parser returned no items, but using RSS content directly for {wechat_url} (content length: {len(processor_result.get('content', ''))} chars)"
            )
            
            # 从processor_result提取信息
            content = processor_result.get("content", "")
            from bs4 import BeautifulSoup
            
            # 将HTML转换为纯文本用于摘要
            try:
                soup = BeautifulSoup(content, 'html.parser')
                text_content = soup.get_text()
                summary = text_content[:500] + "..." if len(text_content) > 500 else text_content
            except Exception as e:
                logger.warning(f"Failed to extract text for summary: {str(e)}", exc_info=True)
                summary = content[:500] + "..." if len(content) > 500 else content
            
            article_data = {
                "title": processor_result.get("title", "微信文章"),
                "summary": clean_html_content(summary),
                "content": clean_html_content(content),
                "original_url": wechat_url,
                "publish_date": pub_date,
                "newspaper_keywords": [],
                "entities": {
                    "wechat_article_rss": True,
                    "source": "rss_content",
                    "digest_date": processor_result.get("digest_date", ""),
                    "issue_number": processor_result.get("issue_number", ""),
                    "parser_failed": True,  # 标记解析失败但保留RSS内容
                },
                "is_processed": False,
            }
            processed_articles_data.append(article_data)
            logger.info(
                f"WeChat Article Fetch: Saved RSS content directly (title: {article_data['title']}, content length: {len(article_data['content'])} chars)"
            )
        else:
            # 原有的fallback逻辑：使用Playwright重新爬取
            logger.info(
                f"WeChat Article Fetch: No specific parser match or no items from parser for {wechat_url}. Falling back to standard processing."
            )

            # Fallback: Use get_standard_article_data
            # Prepare a mock feed_entry if original_rss_entry is not available but processor_result has some data
            fallback_title = "微信文章"
            fallback_summary = None
            fallback_published_parsed = None
            fallback_content_html = processor_result.get(
                "content", ""
            )  # Raw HTML content from crawler

            if original_rss_entry:
                fallback_title = original_rss_entry.title
                if hasattr(original_rss_entry, "summary"):
                    fallback_summary = original_rss_entry.summary
                if hasattr(original_rss_entry, "published_parsed"):
                    fallback_published_parsed = original_rss_entry.published_parsed
            elif processor_result.get("title"):  # Use title from crawler if no RSS entry
                fallback_title = processor_result.get("title")

            # Construct a temporary feedparser-like dict for fallback_feed_entry
            temp_fallback_entry = feedparser.FeedParserDict(
                {
                    "title": fallback_title,
                    "link": wechat_url,
                    "summary": (
                        fallback_summary
                        if fallback_summary
                        else (fallback_content_html[:500] if fallback_content_html else "")
                    ),
                    "published_parsed": fallback_published_parsed,
                    "content": (
                        [{"type": "text/html", "value": fallback_content_html}]
                        if fallback_content_html
                        else []
                    ),
                }
            )

            article_data = await get_standard_article_data(
                article_url=wechat_url,
                article_title=fallback_title,
                fallback_feed_entry=temp_fallback_entry,
            )
            if article_data:
                # Mark as WeChat fallback
                article_data["entities"] = {
                    "wechat_article_fallback": True,
                    "original_wechat_title": fallback_title,
                }
                processed_articles_data.append(article_data)

        return processed_articles_data


def fetch_rss_feed(source: Source, db: Session) -> Tuple[int, bool]:
    logger.info(f"开始抓取RSS: {source.name} ({source.url})")
    _append_source_log(source.id, f"开始抓取RSS: {source.name} ({source.url})")
    max_retries = 3
    retry_delay = 5
    total_new_articles_from_source = 0
    session = _create_http_session()
    
    # 获取时间限制，默认3天
    max_fetch_days = getattr(source, 'max_fetch_days', 3)
    cutoff_date = datetime.now() - timedelta(days=max_fetch_days)
    logger.info(f"时间限制: 只抓取 {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')} 之后的文章")

    for attempt in range(max_retries):
        try:
            logger.info(f"尝试第 {attempt+1}/{max_retries} 次抓取 RSS: {source.url}")
            
            # 添加请求间隔以避免429错误
            if attempt > 0:
                delay = retry_delay * (2 ** attempt)  # 指数退避
                logger.info(f"等待 {delay} 秒后重试...")
                time.sleep(delay)
            
            # Use requests to get the raw content and then unescape HTML entities
            # 使用带重试的会话与浏览器头
            response = session.get(source.url, headers=BROWSER_HEADERS, timeout=30, verify=False)
            
            # 检查HTTP状态码
            if response.status_code == 429:
                logger.warning(f"收到429错误 (Too Many Requests)，等待更长时间...")
                _append_source_log(source.id, "收到429错误 (Too Many Requests)，等待更长时间...")
                # 若已是最后一次重试，则返回错误，避免函数无返回
                if attempt >= max_retries - 1:
                    return (-1, True)
                time.sleep(30)  # 等待30秒
                continue
            elif response.status_code >= 400:
                logger.error(f"HTTP错误 {response.status_code}: {response.text[:200]}")
                _append_source_log(source.id, f"HTTP错误 {response.status_code}: {response.text[:120]}")
                if attempt < max_retries - 1:
                    continue
                return (-1, True)
            
            # 尝试多种解析方法
            feed = None
            
            # 方法1: 直接解析原始内容
            try:
                logger.info("尝试直接解析原始内容...")
                feed = feedparser.parse(response.text)
                if not hasattr(feed, "bozo_exception") or not feed.bozo_exception:
                    logger.info("原始内容解析成功")
                else:
                    logger.warning(f"原始内容解析有警告: {feed.bozo_exception}", exc_info=True)
            except Exception as e:
                logger.warning(f"原始内容解析失败: {e}", exc_info=True)
            
            # 方法2: 如果原始内容解析失败，尝试HTML实体解码后解析
            if not feed or (hasattr(feed, "bozo_exception") and feed.bozo_exception):
                try:
                    logger.info("尝试HTML实体解码后解析...")
                    decoded_content = html.unescape(response.text)
                    
                    # 移除可能导致XML解析错误的字符
                    cleaned_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_content)
                    
                    # 尝试修复常见的XML问题
                    cleaned_content = re.sub(r'&(?![a-zA-Z0-9#]+;)', '&amp;', cleaned_content)
                    
                    feed = feedparser.parse(cleaned_content)
                    if not hasattr(feed, "bozo_exception") or not feed.bozo_exception:
                        logger.info("HTML实体解码后解析成功")
                    else:
                        logger.warning(f"HTML实体解码后解析有警告: {feed.bozo_exception}", exc_info=True)
                except Exception as e:
                    logger.warning(f"HTML实体解码后解析失败: {e}", exc_info=True)
            
            # 方法3: 如果前两种方法都失败，使用BeautifulSoup清理
            if not feed or (hasattr(feed, "bozo_exception") and feed.bozo_exception):
                try:
                    logger.info("尝试BeautifulSoup清理后解析...")
                    from bs4 import BeautifulSoup
                    
                    # 使用XML解析器
                    soup = BeautifulSoup(response.text, 'xml')
                    if soup.find('rss') or soup.find('feed'):
                        # 如果找到RSS/Atom标签，尝试解析清理后的内容
                        cleaned_content = str(soup)
                        feed = feedparser.parse(cleaned_content)
                        if not hasattr(feed, "bozo_exception") or not feed.bozo_exception:
                            logger.info("BeautifulSoup清理后解析成功")
                        else:
                            logger.warning(f"BeautifulSoup清理后解析有警告: {feed.bozo_exception}", exc_info=True)
                    else:
                        logger.warning("BeautifulSoup未找到RSS/Atom标签", exc_info=True)
                except Exception as e:
                    logger.warning(f"BeautifulSoup清理后解析失败: {e}", exc_info=True)
            
            # 如果所有方法都失败
            if not feed:
                logger.error("所有RSS解析方法都失败", exc_info=True)
                if attempt < max_retries - 1:
                    continue
                _append_source_log(source.id, "所有RSS解析方法都失败")
                return (-1, True)

            if hasattr(feed, "bozo_exception") and feed.bozo_exception:
                logger.error(f"RSS解析失败: {feed.bozo_exception}", exc_info=True)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                _append_source_log(source.id, f"RSS解析失败: {feed.bozo_exception}")
                return (-1, True)

            if not hasattr(feed, "entries") or not feed.entries:
                logger.warning(f"RSS源没有条目: {source.url}", exc_info=True)
                _append_source_log(source.id, "RSS源没有条目")
                return (0, False)

            logger.info(f"获取到 {len(feed.entries)} 篇文章从 {source.name}")

            processed_in_batch = 0
            current_batch_article_count = 0  # Number of News items (can be >1 for one feed entry if WeChat parser extracts multiple)

            for i, entry in enumerate(feed.entries):
                articles_data_list: List[Dict[str, Any]] = []

                if (
                    not hasattr(entry, "link")
                    or not entry.link
                    or not hasattr(entry, "title")
                    or not entry.title
                ):
                    logger.warning(
                        f"RSS: 跳过条目 (缺少链接或标题): {getattr(entry, 'link', 'N/A')}"
                    )
                    continue

                # EARLY TIME FILTER: 在抓取内容之前检查RSS条目的发布时间
                entry_publish_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        entry_publish_date = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                        # 如果有时区信息，移除以便比较
                        if entry_publish_date.tzinfo is not None:
                            entry_publish_date = entry_publish_date.replace(tzinfo=None)
                        
                        if entry_publish_date < cutoff_date:
                            logger.info(
                                f"RSS: 跳过过期条目 (RSS发布于 {entry_publish_date}, 截止日期 {cutoff_date}): {entry.title[:30]}..."
                            )
                            continue
                    except (TypeError, ValueError, OverflowError) as e_time:
                        logger.warning(f"RSS: 无法解析RSS条目时间，继续处理: {str(e_time)}", exc_info=True)

                # PRE-FETCH CHECK: Check if this original URL from RSS feed already exists
                # This check is crucial to avoid re-fetching/re-processing already stored articles
                # Query only ID for efficiency, or a minimal set of fields if needed later.
                # For now, just checking existence is enough.
                pre_existing_news_check = (
                    db.query(News.id).filter(News.original_url == entry.link).first()
                )
                if pre_existing_news_check:
                    logger.info(
                        f"RSS: 主链接 {entry.link} (来自RSS条目标题: {entry.title[:30]}...) 已作为新闻存在于数据库中，跳过对此RSS条目的抓取。"
                    )
                    continue  # Skip to the next RSS entry

                if "mp.weixin.qq.com" in entry.link:
                    logger.info(f"RSS: Detected WeChat URL: {entry.link}")
                    # Pass the original entry for potential fallback title/date
                    articles_data_list = asyncio.run(
                        get_wechat_article_data(entry.link, original_rss_entry=entry)
                    )
                else:
                    logger.info(f"RSS: Standard entry: {entry.link}")
                    article_data = asyncio.run(
                        get_rss_entry_article_data(
                            entry,
                            use_newspaper=getattr(
                                source, "use_newspaper", True
                            ),  # 使用源的use_newspaper设置，默认为True
                            use_description_as_summary=getattr(
                                source, "use_description_as_summary", False
                            ),  # 使用源的备选摘要设置，默认为False
                        )
                    )
                    if article_data:
                        articles_data_list.append(article_data)

                if not articles_data_list:
                    logger.info(
                        f"RSS: 未从条目 {entry.link} (RSS标题: {entry.title[:30]}) 获取到有效文章数据（可能由于抓取/解析失败或所有子项已存在），跳过后续处理。"
                    )
                    continue

                newly_added_to_db_this_entry = 0
                for article_data in articles_data_list:
                    # 注意：时间过滤已经在RSS条目级别进行，这里不再重复检查
                    # 但对于微信文章的多个子文章，仍需要进行时间检查（因为子文章可能有不同的时间）
                    if article_data.get("entities", {}).get("wechat_article") and article_data.get("publish_date"):
                        article_date = article_data["publish_date"]
                        if isinstance(article_date, str):
                            try:
                                article_date = datetime.fromisoformat(article_date.replace('Z', '+00:00'))
                            except ValueError:
                                try:
                                    article_date = datetime.strptime(article_date, '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    logger.warning(f"无法解析文章日期: {article_date}", exc_info=True)
                                    article_date = None
                        
                        # 确保两个datetime对象都是naive的（没有时区信息）以便比较
                        if article_date:
                            # 如果article_date有时区信息，转换为本地时间并移除时区信息
                            if article_date.tzinfo is not None:
                                article_date = article_date.replace(tzinfo=None)
                            
                            if article_date < cutoff_date:
                                logger.info(
                                    f"RSS: 跳过过期微信子文章 (发布于 {article_date}, 截止日期 {cutoff_date}): {article_data['title'][:30]}..."
                                )
                                continue
                    
                    # Check if article already exists
                    # For WeChat sub-articles, title + original_url make them unique
                    # For standard articles, original_url is usually unique
                    existing_news_query = db.query(News).filter(
                        News.original_url == article_data["original_url"]
                    )
                    if article_data.get("entities", {}).get(
                        "wechat_article"
                    ):  # Specific check for parsed WeChat sub-items
                        existing_news_query = existing_news_query.filter(
                            News.title == article_data["title"]
                        )

                    existing_news = existing_news_query.first()

                    if existing_news:
                        logger.info(
                            f"RSS: 文章已存在于数据库 (URL: {article_data['original_url']}, Title: {article_data['title'][:20]}...), 跳过。"
                        )
                        continue

                    news = News(
                        source_id=source.id,
                        title=article_data["title"],
                        summary=article_data["summary"],
                        content=article_data["content"],
                        original_url=article_data["original_url"],
                        publish_date=article_data["publish_date"],
                        newspaper_keywords=article_data.get("newspaper_keywords", []),
                        entities=article_data.get("entities"),  # type: ignore
                        is_processed=False,  # All new articles start as unprocessed
                    )

                    # 双重检查：在插入前再次检查，防止并发竞态条件
                    # 对微信文章的多个子条目（URL相同但Title不同）允许插入
                    double_check_query = db.query(News).filter(
                        News.original_url == article_data["original_url"]
                    )
                    if article_data.get("entities", {}).get("wechat_article"):
                        # 微信文章：检查 URL + Title 组合
                        double_check_query = double_check_query.filter(
                            News.title == article_data["title"]
                        )

                    double_check_existing = double_check_query.first()
                    if double_check_existing:
                        logger.warning(
                            f"RSS: 双重检查发现文章已存在（可能并发插入）(URL: {article_data['original_url']}, Title: {article_data['title'][:20]}...), 跳过。"
                        )
                        continue

                    db.add(news)
                    logger.info(
                        f"RSS: 添加新文章到会话: {news.title[:30]}... ({news.original_url})"
                    )
                    newly_added_to_db_this_entry += 1
                    current_batch_article_count += 1

                total_new_articles_from_source += newly_added_to_db_this_entry

                if newly_added_to_db_this_entry > 0:
                    if current_batch_article_count >= 10:
                        logger.info(
                            f"RSS: 批量提交 {current_batch_article_count} 篇文章到数据库"
                        )
                        db.commit()
                        current_batch_article_count = 0

                    delay = random.uniform(2, 4)
                    logger.info(f"RSS: 条目处理后休息 {delay:.2f} 秒...")
                    time.sleep(delay)

            if current_batch_article_count > 0:
                logger.info(
                    f"RSS: 提交剩余 {current_batch_article_count} 篇文章到数据库"
                )
                db.commit()

            source.last_fetch = datetime.now()  # type: ignore
            db.commit()
            logger.info(
                f"RSS抓取完成: {source.name}, 本次总共添加 {total_new_articles_from_source} 篇新文章"
            )
            _append_source_log(source.id, f"RSS抓取完成: 新增 {total_new_articles_from_source} 篇")
            return (total_new_articles_from_source, False)

        except Exception as e:
            logger.error(
                f"RSS抓取失败 (尝试 {attempt+1}/{max_retries}): {source.url}, 错误: {str(e)}",
                exc_info=True,
            )
            _append_source_log(source.id, f"RSS抓取失败: {str(e)}")
            db.rollback()
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return (-1, True)


def get_recent_logs(buffer_name: str = 'crawler'):
    """获取最近的日志"""
    return log_manager.get_recent_logs(buffer_name)


def clear_logs(buffer_name: str = 'crawler'):
    """清空日志缓冲区"""
    return log_manager.clear_logs(buffer_name)


def fetch_webpage(source: Source, db: Session) -> Tuple[int, bool]:
    """抓取网页源"""
    logger.info(f"开始抓取网页: {source.name} ({source.url})")
    _append_source_log(source.id, f"开始抓取网页: {source.name} ({source.url})")
    max_retries = 3
    retry_delay = 5
    total_new_articles = 0

    for attempt in range(max_retries):
        try:
            logger.info(f"尝试第 {attempt+1}/{max_retries} 次抓取网页: {source.url}")
            news_source = newspaper.build(source.url, memoize_articles=False)  # type: ignore
            logger.info(f"找到 {len(news_source.articles)} 个可能的文章链接")

            new_count_this_attempt = 0
            processed_in_batch = 0
            article_limit = 20

            for i, news_article_obj in enumerate(news_source.articles[:article_limit]):
                article_url = news_article_obj.url

                # Check if article already exists by URL (titles can change)
                existing = (
                    db.query(News).filter(News.original_url == article_url).first()
                )
                if existing:
                    logger.info(f"Webpage: 文章已存在，跳过: {article_url}")
                    continue

                try:
                    logger.info(f"Webpage: 抓取文章 #{i+1}: {article_url}")
                    delay = random.uniform(2, 3)
                    logger.info(f"Webpage: 休息 {delay:.2f} 秒后开始抓取...")
                    time.sleep(delay)

                    # news_article_obj.title might be None before download/parse
                    # Provide a fallback title if needed for get_standard_article_data
                    initial_title = (
                        news_article_obj.title if news_article_obj.title else "网页文章"
                    )

                    article_data = asyncio.run(
                        get_standard_article_data(
                            article_url=article_url,
                            article_title=initial_title,  # Pass title hint
                            existing_article_obj=news_article_obj,  # Pass the newspaper.Article object
                        )
                    )

                    if not article_data or not article_data.get("content"):
                        logger.warning(f"Webpage: 未能从 {article_url} 获取有效内容。")
                        continue

                    # Ensure content is substantial enough
                    if len(article_data["content"]) < 200:
                        logger.warning(
                            f"Webpage: 文章内容过短 ({len(article_data['content'])} chars) for {article_url}, 跳过。"
                        )
                        continue

                    news = News(
                        source_id=source.id,
                        title=article_data["title"],  # Use title from fetched data
                        summary=article_data["summary"],
                        content=article_data["content"],
                        original_url=article_data["original_url"],
                        publish_date=article_data["publish_date"],
                        newspaper_keywords=article_data.get("newspaper_keywords", []),
                        entities=article_data.get("entities"),  # type: ignore
                        is_processed=False,
                    )

                    # 双重检查：在插入前再次检查，防止并发竞态条件
                    double_check_existing = (
                        db.query(News).filter(News.original_url == article_data["original_url"]).first()
                    )
                    if double_check_existing:
                        logger.warning(
                            f"Webpage: 双重检查发现文章已存在（可能并发插入）(URL: {article_data['original_url']}), 跳过。"
                        )
                        continue

                    db.add(news)
                    new_count_this_attempt += 1
                    processed_in_batch += 1
                    logger.info(f"Webpage: 添加新网页文章到会话: {news.title[:30]}...")

                    if processed_in_batch >= 5:
                        logger.info(
                            f"Webpage: 批量提交 {processed_in_batch} 篇网页文章"
                        )
                        db.commit()
                        processed_in_batch = 0

                except Exception as e_article:
                    logger.error(
                        f"Webpage: 处理文章失败: {article_url}, 错误: {str(e_article)}",
                        exc_info=True,
                    )
                    # db.rollback() # Rollback for this article? Or let batch commit handle it.
                    # For now, continue to next article.
                    continue

            if processed_in_batch > 0:
                logger.info(f"Webpage: 提交剩余 {processed_in_batch} 篇网页文章")
                db.commit()

            total_new_articles += new_count_this_attempt
            source.last_fetch = datetime.now()  # type: ignore
            db.commit()
            logger.info(
                f"网页抓取完成: {source.name}, 本次尝试新增 {new_count_this_attempt} 篇文章"
            )
            _append_source_log(source.id, f"网页抓取完成: 新增 {new_count_this_attempt} 篇 (累计 {total_new_articles})")
            return (total_new_articles, False)

        except Exception as e_wp_main:
            logger.error(
                f"网页抓取失败 (尝试 {attempt+1}/{max_retries}): {source.url}, 错误: {str(e_wp_main)}",
                exc_info=True,
            )
            _append_source_log(source.id, f"网页抓取失败: {str(e_wp_main)}")
            db.rollback()
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            return (-1, True)


def crawl_source(source_id: int):
    """抓取指定源的内容"""
    db = SessionLocal()
    start_time = datetime.now()
    source: Optional[Source] = None  # Define source here for broader scope

    try:
        source = db.query(Source).filter(Source.id == source_id).first()

        if not source:
            logger.error(f"源不存在: ID {source_id}")
            return {
                "status": "error",
                "message": f"源不存在: ID {source_id}",
                "count": 0,
            }

        if not source.active:  # type: ignore
            logger.warning(f"源未激活: {source.name} (ID: {source_id})")  # type: ignore
            # ... (rest of inactive logic, ensure source attributes are accessed safely)
            result = {"status": "warning", "message": f"源未激活: {source.name}", "count": 0}  # type: ignore
            source.last_fetch_status = result["status"]  # type: ignore
            source.last_fetch_result = result  # type: ignore
            db.commit()
            return result

        if source.last_fetch:  # type: ignore
            time_since_last_fetch = datetime.now() - source.last_fetch  # type: ignore
            if time_since_last_fetch.total_seconds() < source.fetch_interval:  # type: ignore
                remaining_time = source.fetch_interval - time_since_last_fetch.total_seconds()  # type: ignore
                logger.info(f"源 {source.name} 最近已抓取，还需等待 {remaining_time:.0f} 秒")  # type: ignore
                # ... (rest of skipped logic)
                result = {
                    "status": "skipped",
                    "message": f"源最近已抓取，还需等待 {remaining_time:.0f} 秒",
                    "count": 0,
                }
                source.last_fetch_status = result["status"]  # type: ignore
                source.last_fetch_result = result  # type: ignore
                db.commit()
                return result

        logger.info(f"开始抓取源: {source.name} (ID: {source_id}), 类型: {source.type.value}")  # type: ignore

        new_count = 0
        had_error = False
        if source.type == SourceType.RSS:  # type: ignore
            new_count, had_error = fetch_rss_feed(source, db)  # type: ignore
        elif source.type == SourceType.WEBPAGE:  # type: ignore
            new_count, had_error = fetch_webpage(source, db)  # type: ignore
        else:
            logger.error(f"不支持的源类型: {source.type}")  # type: ignore
            # ... (rest of unsupported type logic)
            result = {"status": "error", "message": f"不支持的源类型: {source.type}", "count": 0}  # type: ignore
            source.last_fetch_status = result["status"]  # type: ignore
            source.last_fetch_result = result  # type: ignore
            source.last_fetch = datetime.now()  # type: ignore
            db.commit()
            return result

        # After fetching, if new_count > 0, process them
        if new_count > 0 and not had_error:
            logger.info(f"成功抓取 {new_count} 篇新文章，开始LLM处理...")
            try:
                process_new_articles(source_id, db)  # Pass source_id
            except Exception as e_proc:
                logger.error(f"处理新文章失败: {str(e_proc)}", exc_info=True)
        else:
            logger.info(f"源 {source.name} 没有抓取到新文章")  # type: ignore
        if had_error:
            logger.warning("抓取过程中发生错误（已记录详细日志）", exc_info=True)

        execution_time = (datetime.now() - start_time).total_seconds()
        final_result_status = "error" if had_error else "success"

        final_result = {
            "status": final_result_status,
            "message": f"抓取完成，新增 {new_count} 篇文章",
            "count": new_count,
            "execution_time": f"{execution_time:.2f}秒",
        }
        source.last_fetch_status = final_result["status"]  # type: ignore
        source.last_fetch_result = final_result  # type: ignore
        # last_fetch time is updated within fetch_rss_feed/fetch_webpage upon their successful completion
        # If they fail and return 0 after retries, last_fetch might not be updated there.
        # Update here as a safeguard if new_count might be 0 due to actual "no new articles" vs error.
        if source.last_fetch_status == "success":  # type: ignore # only update if this overall crawl_source call is deemed successful
            source.last_fetch = datetime.now()  # type: ignore

        db.commit()
        return final_result

    except Exception as e:
        db.rollback()
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"抓取任务失败 for source_id {source_id}: {str(e)}", exc_info=True)

        # Attempt to update source status even on failure
        if source:  # Check if source was successfully fetched
            try:
                error_result = {
                    "status": "error",
                    "message": f"抓取失败: {str(e)}",
                    "count": 0,
                    "execution_time": f"{execution_time:.2f}秒",
                }
                source.last_fetch = datetime.now()  # type: ignore
                source.last_fetch_status = "error"  # type: ignore
                source.last_fetch_result = error_result  # type: ignore
                db.commit()
            except Exception as ex_commit:
                logger.error(f"更新源状态失败 after error: {str(ex_commit)}", exc_info=True)
                db.rollback()  # Rollback the failed status update attempt

        return {
            "status": "error",
            "message": f"抓取失败: {str(e)}",
            "count": 0,
            "execution_time": f"{execution_time:.2f}秒",
        }
    finally:
        db.close()


def process_new_articles(source_id: int, db: Session):
    """处理新抓取的文章 (LLM processing)"""
    # Query for articles from this source_id that are not yet processed by LLM
    new_articles_to_llm_process = (
        db.query(News)
        .filter(News.source_id == source_id, News.is_processed == False)
        .all()
    )

    logger.info(
        f"准备LLM处理 {len(new_articles_to_llm_process)} 篇来自源ID {source_id} 的新文章"
    )

    for i, article_to_llm in enumerate(new_articles_to_llm_process, 1):
        try:
            logger.info(
                f"LLM处理文章 {i}/{len(new_articles_to_llm_process)}: ID {article_to_llm.id}, 标题: {article_to_llm.title[:50]}..."
            )
            process_news(article_to_llm, db)  # type: ignore # This is the LLM processor
            logger.info(f"文章 ID {article_to_llm.id} LLM处理完成")
            db.commit()  # Commit after each successful LLM processing

            if i < len(new_articles_to_llm_process):
                delay = random.uniform(2, 3)
                logger.info(f"LLM处理后休息 {delay:.2f} 秒...")
                time.sleep(delay)
        except Exception as e:
            logger.error(
                f"LLM处理文章失败: ID {article_to_llm.id}, 错误: {str(e)}",
                exc_info=True,
            )
            db.rollback()  # Rollback if LLM processing for one article fails

    logger.info(f"源ID {source_id} 的所有新文章LLM处理完成")


def trigger_source_crawl(source_id: int):
    """
    手动触发单个源的抓取，并创建TaskExecution记录

    Args:
        source_id: 要抓取的源ID

    Returns:
        包含执行结果的字典，包括execution_id（数据库记录ID）
    """
    db = SessionLocal()
    execution = None

    try:
        # 获取源信息
        source = db.query(Source).filter(Source.id == source_id).first()
        source_name = source.name if source else f"ID:{source_id}"

        # 创建TaskExecution记录
        task_id = str(uuid.uuid4())
        execution = TaskExecution.create_task_start(
            db=db,
            task_type='manual_crawl_source',
            task_id=task_id,
            message=f'手动触发抓取: {source_name}',
            details={
                'source_id': source_id,
                'source_name': source_name,
                'trigger_type': 'manual'
            }
        )

        logger.info(f"手动触发对源 ID {source_id} ({source_name}) 的抓取，任务ID: {task_id}, 执行记录ID: {execution.id}")

        # 执行抓取
        result = crawl_source(source_id)

        # 根据抓取结果更新TaskExecution记录
        status = result.get("status", "unknown")
        message = result.get("message", "未知结果")
        count = result.get("count", 0)

        # 确定任务状态
        if status == "success":
            task_status = 'success'
        elif status == "skipped":
            task_status = 'info'
        elif status == "error":
            task_status = 'error'
        else:
            task_status = 'warning'

        # 完成TaskExecution记录
        execution.complete_task(
            db=db,
            status=task_status,
            message=message,
            details={
                'source_id': source_id,
                'source_name': source_name,
                'trigger_type': 'manual',
                'crawl_status': status,
                'articles_found': count
            },
            items_processed=1,  # 处理了1个源
            items_success=1 if status == "success" else 0,
            items_failed=1 if status == "error" else 0
        )

        logger.info(f"抓取任务 {task_id} (执行记录 {execution.id}) 完成: {status}, {message}")

        # 返回响应
        return {
            "execution_id": execution.id,  # 返回数据库记录ID
            "task_id": task_id,
            "status": status,
            "message": message,
            "count": count,
            "start_time": execution.start_time.isoformat(),
            "end_time": execution.end_time.isoformat() if execution.end_time else None,
            "execution_time": f"{execution.duration_seconds}秒" if execution.duration_seconds else None,
        }

    except Exception as e:
        # 如果有异常，标记任务失败
        error_msg = f"抓取失败: {str(e)}"
        logger.error(error_msg, exc_info=True)

        if execution:
            execution.fail_task(
                db=db,
                error_message=error_msg,
                error_type=type(e).__name__,
                stack_trace=traceback.format_exc(),
                details={
                    'source_id': source_id,
                    'trigger_type': 'manual'
                }
            )

        return {
            "execution_id": execution.id if execution else None,
            "task_id": task_id if 'task_id' in locals() else None,
            "status": "error",
            "message": error_msg,
            "count": 0,
            "start_time": execution.start_time.isoformat() if execution else None,
            "end_time": execution.end_time.isoformat() if execution and execution.end_time else None,
            "execution_time": None,
        }
    finally:
        db.close()


def schedule_all_crawling():
    logger.info("开始定期调度所有活跃源的抓取")
    start_time = datetime.now()
    results = {
        "total_sources": 0,
        "successful_crawls": 0,
        "failed_crawls": 0,
        "skipped_crawls": 0,
        "total_articles_added": 0,
        "details": [],
    }

    db = SessionLocal()
    try:
        active_sources = db.query(Source).filter(Source.active == True).all()
        results["total_sources"] = len(active_sources)

        if not active_sources:
            logger.info("没有活跃的源需要抓取")
            return results

        logger.info(f"找到 {len(active_sources)} 个活跃的源")

        for (
            source_obj
        ) in active_sources:  # Renamed source to source_obj to avoid conflict
            try:
                # Check interval time directly here as crawl_source will also do it,
                # but this saves a call to crawl_source if skipped.
                if source_obj.last_fetch:  # type: ignore
                    time_since_last = datetime.now() - source_obj.last_fetch  # type: ignore
                    if time_since_last.total_seconds() < source_obj.fetch_interval:  # type: ignore
                        logger.info(f"源 {source_obj.name} (ID: {source_obj.id}) 未到抓取时间，跳过")  # type: ignore
                        results["skipped_crawls"] += 1
                        results["details"].append(
                            {
                                "source_id": source_obj.id,
                                "source_name": source_obj.name,  # type: ignore
                                "status": "skipped",
                                "message": "未到抓取时间",
                                "articles_added": 0,
                            }
                        )
                        continue

                logger.info(f"调度源 {source_obj.name} (ID: {source_obj.id}) 抓取")  # type: ignore
                # trigger_source_crawl calls crawl_source which handles its own DB session
                crawl_result = trigger_source_crawl(source_obj.id)  # type: ignore

                results["details"].append(
                    {
                        "source_id": source_obj.id,
                        "source_name": source_obj.name,  # type: ignore
                        "status": crawl_result["status"],
                        "message": crawl_result["message"],
                        "articles_added": crawl_result["count"],
                    }
                )

                if crawl_result["status"] == "success":
                    results["successful_crawls"] += 1
                    results["total_articles_added"] += crawl_result["count"]
                elif (
                    crawl_result["status"] == "skipped"
                ):  # Should be caught above, but as safeguard
                    results["skipped_crawls"] += 1
                else:  # error or warning
                    results["failed_crawls"] += 1

                # Delay between processing different sources
                delay = random.uniform(5, 10)
                logger.info(f"休息 {delay:.2f} 秒后处理下一个源...")
                time.sleep(delay)

            except Exception as e_schedule_item:
                logger.error(f"调度源 {source_obj.name} (ID: {source_obj.id}) 时出错: {str(e_schedule_item)}", exc_info=True)  # type: ignore
                results["failed_crawls"] += 1
                results["details"].append(
                    {
                        "source_id": source_obj.id,
                        "source_name": source_obj.name,  # type: ignore
                        "status": "error",
                        "message": f"调度层错误: {str(e_schedule_item)}",
                        "articles_added": 0,
                    }
                )

        execution_time_total = (datetime.now() - start_time).total_seconds()
        results["execution_time"] = f"{execution_time_total:.2f}秒"  # type: ignore
        logger.info(
            f"所有源调度完成，用时: {results['execution_time']}，"
            f"成功抓取源数: {results['successful_crawls']} (共添加 {results['total_articles_added']} 文章)，"
            f"失败: {results['failed_crawls']}，跳过: {results['skipped_crawls']}"
        )
        return results

    except Exception as e_schedule_main:
        logger.error(f"整体调度任务失败: {str(e_schedule_main)}", exc_info=True)
        # results["error_message"] = str(e_schedule_main) # type: ignore
        return results  # Return partially filled results
    finally:
        db.close()
