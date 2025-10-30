
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import List

from app.models.news import News
from app.models.digest import Digest
from app.models.scheduler_config import SchedulerConfig
from app.services.llm_processor import LLMProcessor

logger = logging.getLogger(__name__)

class NewsDuplicateDetector:
    """
    服务于检测新闻是否在近期快报中重复出现。
    """
    def __init__(self, db: Session):
        self.db = db
        self.llm_processor = LLMProcessor(db=db)

    def get_historical_news(self, days: int) -> List[News]:
        """
        获取过去N天内已发布快报中的所有新闻。

        :param days: 要回顾的天数。
        :return: 过去N天内快报中的新闻列表。
        """
        if days <= 0:
            return []
        
        start_date = datetime.now() - timedelta(days=days)
        
        # 查找在指定日期之后创建的快报
        recent_digests = self.db.query(Digest).filter(Digest.created_at >= start_date).all()
        
        historical_news_ids = set()
        for digest in recent_digests:
            for news_item in digest.news_items:
                historical_news_ids.add(news_item.id)
        
        if not historical_news_ids:
            return []
            
        # 获取新闻对象
        historical_news = self.db.query(News).filter(News.id.in_(list(historical_news_ids))).all()
        
        logger.info(f"找到过去 {days} 天内快报中的 {len(historical_news)} 条历史新闻。")
        return historical_news

    def check_duplicates(self, news_to_check: News, historical_news: List[News]) -> bool:
        """
        使用LLM检查单条新闻是否与历史新闻列表中的任何一条重复。

        :param news_to_check: 需要检查的单条新闻。
        :param historical_news: 历史新闻列表。
        :return: 如果重复则返回 True，否则返回 False。
        """
        if not historical_news:
            return False

        # 构建用于LLM提示的上下文
        historical_titles = "\n".join([f"- {n.title}" for n in historical_news])
        prompt = f"""
        请判断以下“新新闻”是否与“历史新闻列表”中的任何一条新闻内容相似或重复。

        “历史新闻列表”:
        {historical_titles}

        “新新闻”:
        - 标题: {news_to_check.title}
        - 摘要: {news_to_check.summary or '无'}

        请仔细评估内容，而不仅仅是标题。如果“新新闻”的主题、事件或核心信息在“历史新闻列表”中已经出现过，请回答“是”，否则回答“否”。
        """
        
        try:
            response = self.llm_processor.generate_text(prompt, model="deepseek-v2-chat") # 使用一个合适的模型
            
            # 对LLM的回答进行解析
            answer = response.strip().lower()
            if '是' in answer:
                logger.info(f"检测到重复新闻: '{news_to_check.title}'")
                return True
            else:
                logger.info(f"新闻 '{news_to_check.title}' 未发现重复。")
                return False
        except Exception as e:
            logger.error(f"调用LLM进行新闻查重时出错: {e}")
            # 在LLM调用失败的情况下，默认为不重复，以避免阻碍正常流程
            return False

    @classmethod
    def get_duplicate_check_days(cls, db: Session) -> int:
        """从数据库获取重复新闻检查的天数配置"""
        return SchedulerConfig.get_value(db, "news_duplicate_check_days", default_value=3, value_type="int")


