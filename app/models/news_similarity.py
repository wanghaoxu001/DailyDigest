"""
新闻相似度关系模型
用于存储预计算的文章相似关系，提高前端响应速度
"""

from sqlalchemy import Column, Integer, Float, DateTime, Index, String, Text, Boolean
from sqlalchemy.sql import func
from app.db.base import Base


class NewsSimilarity(Base):
    """新闻相似度关系表"""
    __tablename__ = "news_similarity"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 新闻对
    news_id_1 = Column(Integer, nullable=False, comment="新闻1的ID")
    news_id_2 = Column(Integer, nullable=False, comment="新闻2的ID")
    
    # 相似度分数
    similarity_score = Column(Float, nullable=False, comment="综合相似度分数(0-1)")
    entity_similarity = Column(Float, default=0.0, comment="实体相似度分数")
    text_similarity = Column(Float, default=0.0, comment="文本相似度分数")
    
    # 分组信息
    group_id = Column(String(50), nullable=True, comment="事件分组ID")
    is_same_event = Column(Boolean, default=False, comment="是否为同一事件")
    
    # 元数据
    calculation_version = Column(String(20), default="v1.0", comment="计算算法版本")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), comment="更新时间")
    
    # 索引优化
    __table_args__ = (
        # 确保同一对新闻只有一条记录（较小的ID在前）
        Index('ix_news_similarity_pair', 'news_id_1', 'news_id_2', unique=True),
        # 按相似度分数查询的索引
        Index('ix_news_similarity_score', 'similarity_score'),
        # 按分组查询的索引
        Index('ix_news_similarity_group', 'group_id'),
        # 按创建时间查询的索引
        Index('ix_news_similarity_created_at', 'created_at'),
        # 复合索引用于查找特定新闻的相似文章
        Index('ix_news_similarity_news1_score', 'news_id_1', 'similarity_score'),
        Index('ix_news_similarity_news2_score', 'news_id_2', 'similarity_score'),
    )


class NewsEventGroup(Base):
    """新闻事件分组表"""
    __tablename__ = "news_event_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 分组信息
    group_id = Column(String(50), unique=True, nullable=False, comment="事件分组唯一ID")
    event_label = Column(String(500), nullable=False, comment="事件标签/标题")
    
    # 主要新闻（代表性新闻）
    primary_news_id = Column(Integer, nullable=False, comment="主要新闻ID")
    
    # 统计信息
    news_count = Column(Integer, default=1, comment="包含的新闻数量")
    sources_count = Column(Integer, default=1, comment="涉及的新闻源数量")
    
    # 实体信息（JSON格式存储）
    key_entities = Column(Text, comment="关键实体信息(JSON)")
    
    # 分组设置
    similarity_threshold = Column(Float, default=0.75, comment="使用的相似度阈值")
    calculation_version = Column(String(20), default="v1.0", comment="计算算法版本")
    
    # 时间范围
    earliest_news_time = Column(DateTime(timezone=True), comment="最早新闻时间")
    latest_news_time = Column(DateTime(timezone=True), comment="最新新闻时间")
    
    # 元数据
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), comment="更新时间")
    
    # 索引
    __table_args__ = (
        Index('ix_news_event_groups_group_id', 'group_id'),
        Index('ix_news_event_groups_primary_news', 'primary_news_id'),
        Index('ix_news_event_groups_created_at', 'created_at'),
        Index('ix_news_event_groups_news_count', 'news_count'),
    )


class NewsGroupMembership(Base):
    """新闻分组成员关系表"""
    __tablename__ = "news_group_membership"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 关联关系
    group_id = Column(String(50), nullable=False, comment="事件分组ID")
    news_id = Column(Integer, nullable=False, comment="新闻ID")
    
    # 在分组中的角色
    is_primary = Column(Boolean, default=False, comment="是否为主要新闻")
    similarity_to_primary = Column(Float, default=0.0, comment="与主要新闻的相似度")
    
    # 元数据
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    
    # 索引
    __table_args__ = (
        # 确保同一新闻在同一分组中只有一条记录
        Index('ix_news_group_membership_unique', 'group_id', 'news_id', unique=True),
        # 按分组查询成员
        Index('ix_news_group_membership_group', 'group_id'),
        # 按新闻查询所属分组
        Index('ix_news_group_membership_news', 'news_id'),
        # 查询主要新闻
        Index('ix_news_group_membership_primary', 'is_primary'),
    ) 