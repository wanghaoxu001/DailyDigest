import re
from datetime import datetime
from typing import Dict, Any, Optional

from . import BaseArticleParser


class SecurityDigestParser(BaseArticleParser):
    """5th域安全微讯早报解析器
    """

    def __init__(self, content: str, metadata: Optional[Dict[str, str]] = None):
        """初始化解析器

        Args:
            content: 爬取的原始内容文本
            metadata: 外部元数据（可选），包含 title, date, issue_number 等
        """
        super().__init__(content)
        self.metadata = metadata or {}
        self.title = self.metadata.get("title", "")
        self.digest_date = self.metadata.get("date", "")
        self.issue_number = self.metadata.get("issue_number", "")
        self.author = self.metadata.get("author", "")
        self.publish_time = self.metadata.get("publish_time", "")
        self.news_items = []
        self.categories = {
            "政策法规": [],
            "安全事件": [],
            "漏洞预警": [],
            "风险预警": [],
            "恶意软件": [],
        }
        self.simple_mode = False  # 是否使用简化模式

    def parse(self) -> Dict[str, Any]:
        """解析5th域安全微讯早报内容

        Returns:
            Dict: 结构化的5th域安全微讯早报数据
        """
        print("SecurityDigestParser: 使用简化模式解析RSS内容")
        self.simple_mode = True
        return self._parse_simple_mode()
    
    def _parse_simple_mode(self) -> Dict[str, Any]:
        """简化模式解析（RSS HTML内容）
        
        从编号列表中提取所有新闻，不区分分类
        """
        # 如果metadata没有提供基本信息，尝试从内容中提取
        if not self.title or not self.digest_date or not self.issue_number:
            self._parse_basic_info()
        
        # 提取所有编号的新闻标题
        title_dict = self._extract_title_list_from_html()
        
        # 转换为news_items格式
        for news_id, title in sorted(title_dict.items()):
            self.news_items.append({
                "id": news_id,
                "title": title,
                "content": title,  # 简化模式下，内容就是标题
                "summary": title,
                "category": "未分类",  # RSS模式无分类
            })
        
        # 构建结果
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

    def _extract_title_list_from_html(self) -> Dict[int, str]:
        """从HTML内容中提取新闻标题列表（用于RSS HTML）
        
        RSS HTML格式：每条新闻在独立的 <p> 标签中，格式为 "数字.标题"
        
        Returns:
            Dict[int, str]: 编号到标题的映射
        """
        from bs4 import BeautifulSoup
        
        title_dict = {}
        
        try:
            soup = BeautifulSoup(self.raw_content, 'html.parser')
            
            # 方法1: 从 <p> 标签中提取
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                # 匹配 "数字.标题" 格式（数字和点号之间可能没有空格）
                match = re.match(r'^(\d+)\.(.+)$', text)
                if match:
                    news_id = int(match.group(1))
                    title = match.group(2).strip()
                    # 过滤一些无效标题
                    if title and len(title) > 3 and title not in ['备注:', '个性化专题资讯信息，欢迎订阅！']:
                        title_dict[news_id] = title
            
            # 如果方法1没找到，尝试方法2：从纯文本中提取
            if not title_dict:
                text_content = soup.get_text()
                lines = text_content.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 匹配 "编号.标题" 或 "编号. 标题"
                    match = re.match(r'^(\d+)\.\s*(.+)$', line)
                    if match:
                        news_id = int(match.group(1))
                        title = match.group(2).strip()
                        if title and len(title) > 3:
                            title_dict[news_id] = title
            
            print(f"SecurityDigestParser: 从HTML中提取了 {len(title_dict)} 条新闻标题")
            
            # 调试：显示前5条
            if title_dict:
                for i, (news_id, title) in enumerate(sorted(title_dict.items())[:5], 1):
                    print(f"  {news_id}. {title[:60]}...")
            
        except Exception as e:
            print(f"SecurityDigestParser: 从HTML提取标题时出错: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return title_dict

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
