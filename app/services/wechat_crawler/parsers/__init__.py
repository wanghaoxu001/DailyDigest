"""
文章解析器包

这个包包含不同类型微信文章的解析器实现
"""

from typing import Dict, Any, Type, List


# 解析器基类
class BaseArticleParser:
    """文章解析器基类"""

    def __init__(self, content: str):
        """初始化解析器

        Args:
            content: 文章内容
        """
        self.raw_content = content

    def parse(self) -> Dict[str, Any]:
        """解析文章内容

        Returns:
            Dict: 解析结果
        """
        raise NotImplementedError("子类必须实现parse方法")


# 未来可以导入其他解析器
# from .security_digest_parser import SecurityDigestParser
# from .tech_news_parser import TechNewsParser
