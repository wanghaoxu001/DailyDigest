from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

from app.db.base import Base


class EventGroup(Base):
    """事件分组缓存表"""
    __tablename__ = "event_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(String(100), unique=True, index=True, comment="分组唯一标识")
    
    # 事件基本信息
    event_label = Column(String(200), comment="事件标签")
    news_count = Column(Integer, default=1, comment="新闻数量")
    sources = Column(JSON, comment="新闻源列表")
    
    # 主要新闻和相关新闻ID列表
    primary_news_id = Column(Integer, comment="主要新闻ID")
    related_news_ids = Column(JSON, comment="相关新闻ID列表")
    
    # 相似度分数和实体信息
    similarity_scores = Column(JSON, comment="相似度分数")
    entities = Column(JSON, comment="提取的实体信息")
    
    # 标记信息
    is_standalone = Column(Boolean, default=False, comment="是否为独立新闻")
    
    # 查询条件（用于缓存失效判断）
    hours = Column(Integer, default=24, comment="时间范围（小时）")
    categories = Column(JSON, comment="分类筛选条件")
    source_ids = Column(JSON, comment="新闻源筛选条件")
    exclude_used = Column(Boolean, default=False, comment="是否排除已用于快报的新闻")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    def __repr__(self):
        return f"<EventGroup(id={self.id}, event_label='{self.event_label}', news_count={self.news_count})>" 