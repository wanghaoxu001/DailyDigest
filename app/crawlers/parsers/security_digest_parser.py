import re
import json
from datetime import datetime
from typing import Dict, List, Any, Tuple

from . import BaseArticleParser


class SecurityDigestParser(BaseArticleParser):
    """5th域安全微讯早报解析器"""

    def __init__(self, content: str):
        """初始化解析器

        Args:
            content: 爬取的原始内容文本
        """
        super().__init__(content)
        self.title = ""
        self.digest_date = ""
        self.issue_number = ""
        self.author = ""
        self.publish_time = ""
        self.news_items = []
        self.categories = {
            "政策法规": [],
            "安全事件": [],
            "漏洞预警": [],
            "风险预警": [],
            "恶意软件": [],
        }

    def parse(self) -> Dict[str, Any]:
        """解析5th域安全微讯早报内容

        Returns:
            Dict: 结构化的5th域安全微讯早报数据
        """
        # 解析基本信息
        self._parse_basic_info()

        # 解析新闻标题列表
        title_list = self._extract_title_list()

        # 解析详细内容
        self._extract_detailed_content()

        # 匹配标题和详细内容
        self._match_titles_with_content(title_list)

        # 构建结构化结果
        return self._build_result()

    def _parse_basic_info(self):
        """解析快报的基本信息：标题、日期、期号等"""
        # 提取快报标题
        title_match = re.search(r"(.*?)【(\d+)】(\d+)期", self.raw_content)
        if title_match:
            self.title = title_match.group(1).strip()
            self.digest_date = title_match.group(2)
            self.issue_number = title_match.group(3)

        # 提取作者和发布时间
        author_match = re.search(r"作者:\s?(.*?)\n", self.raw_content)
        if author_match:
            self.author = author_match.group(1).strip()

        time_match = re.search(r"发布时间:\s?(.*?)\n", self.raw_content)
        if time_match:
            self.publish_time = time_match.group(1).strip()

    def _extract_title_list(self) -> Dict[int, str]:
        """提取5th域安全微讯早报开头的新闻标题列表

        Returns:
            Dict[int, str]: 编号到标题的映射
        """
        # 查找标题列表部分的文本
        title_list_section = re.search(r"((?:\d+\.\s.*?\n)+)", self.raw_content)
        if not title_list_section:
            return {}

        # 提取单个标题行
        title_lines = title_list_section.group(1).strip().split("\n")
        title_dict = {}

        for line in title_lines:
            # 匹配形如 "1. 标题内容" 的行
            match = re.match(r"(\d+)\.\s(.*?)$", line.strip())
            if match:
                news_id = int(match.group(1))
                title = match.group(2).strip()
                title_dict[news_id] = title

        return title_dict

    def _extract_detailed_content(self):
        """提取分类和每条新闻的详细内容"""
        # 找出所有分类标题
        category_positions = []
        for category in self.categories.keys():
            match = re.search(f"{category}\n", self.raw_content)
            if match:
                category_positions.append((match.start(), category))

        # 按位置排序
        category_positions.sort()

        # 提取每个分类下的内容
        for i, (pos, category) in enumerate(category_positions):
            # 确定当前分类内容的结束位置
            if i < len(category_positions) - 1:
                end_pos = category_positions[i + 1][0]
            else:
                # 最后一个分类，查找"往期推荐"或文章结尾
                end_match = re.search(r"往期推荐", self.raw_content[pos:])
                if end_match:
                    end_pos = pos + end_match.start()
                else:
                    end_pos = len(self.raw_content)

            # 提取当前分类的内容
            category_content = self.raw_content[pos:end_pos].strip()

            # 从分类内容中提取每条新闻
            self._parse_category_news(category, category_content)

    def _parse_category_news(self, category: str, content: str):
        """解析某个分类下的所有新闻

        Args:
            category: 分类名称
            content: 该分类下的原始内容
        """
        # 跳过分类标题行
        content_lines = content.split("\n")[1:]
        if not content_lines:
            return

        current_news = {
            "category": category,
            "title": "",
            "content": "",
            "summary": "",
            "id": 0,
        }
        news_started = False

        for line in content_lines:
            # 检测新闻的开始，形如 "1. 标题内容"
            news_match = re.match(r"(\d+)\.\s(.*?)$", line.strip())

            if news_match:
                # 如果已经有一条新闻在处理中，先保存它
                if news_started and current_news["title"]:
                    current_news["summary"] = current_news["content"]
                    self.categories[category].append(current_news.copy())

                # 开始新的新闻
                news_id = int(news_match.group(1))
                news_title = news_match.group(2).strip()
                current_news = {
                    "category": category,
                    "title": news_title,
                    "content": "",
                    "id": news_id,
                }
                news_started = True
            elif news_started:
                # 累积新闻内容
                if line.strip():
                    if current_news["content"]:
                        current_news["content"] += "\n" + line.strip()
                    else:
                        current_news["content"] = line.strip()

        # 保存最后一条新闻
        if news_started and current_news["title"]:
            self.categories[category].append(current_news.copy())

    def _match_titles_with_content(self, title_dict: Dict[int, str]):
        """将标题列表与详细内容匹配

        Args:
            title_dict: 编号到标题的映射
        """
        # 将所有分类下的新闻合并到一个列表
        all_news = []
        for category, news_list in self.categories.items():
            all_news.extend(news_list)

        # 遍历所有新闻，确保标题与标题列表一致
        for news in all_news:
            news_id = news["id"]
            if news_id in title_dict:
                # 确保新闻标题一致性
                if news["title"] != title_dict[news_id]:
                    # 如果不一致，使用标题列表中的标题（通常更准确）
                    news["original_title"] = news["title"]
                    news["title"] = title_dict[news_id]

            # 添加到最终的新闻列表
            self.news_items.append(news)

    def _build_result(self) -> Dict[str, Any]:
        """构建最终的结构化数据结果

        Returns:
            Dict: 结构化的5th域安全微讯早报
        """
        return {
            "title": self.title,
            "date": self.digest_date,
            "issue_number": self.issue_number,
            "author": self.author,
            "publish_time": self.publish_time,
            "news_count": len(self.news_items),
            "news_items": self.news_items,
            "categories": self.categories,
            "parsed_time": datetime.now().isoformat(),
            "parser_type": "security_digest",
        }
