from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    Enum,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class NewsCategory(enum.Enum):
    FINANCIAL = "金融业网络安全事件"  # 金融业网络安全事件
    MAJOR = "重大网络安全事件"  # 重大网络安全事件
    DATA_LEAK = "重大数据泄露事件"  # 重大数据泄露事件
    VULNERABILITY = "重大漏洞风险提示"  # 重大漏洞风险提示
    OTHER = "其他"  # 其他


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"))
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    original_url = Column(String(500), nullable=False)
    original_language = Column(String(50), nullable=True)

    # 处理后的数据
    generated_title = Column(String(500), nullable=True)  # AI生成的一句话标题
    generated_summary = Column(Text, nullable=True)  # AI生成的摘要
    article_summary = Column(Text, nullable=True)  # 详细文章总结（Markdown格式）
    summary_source = Column(
        String(50), nullable=True
    )  # 摘要来源：'original'(原文摘要)或'generated'(AI生成)
    category = Column(Enum(NewsCategory), nullable=True)  # 分类
    entities = Column(JSON, nullable=True)  # 提取的实体
    newspaper_keywords = Column(JSON, nullable=True)  # Newspaper4k提取的关键词
    tokens_usage = Column(JSON, nullable=True)  # API消耗的tokens信息

    # 后续处理标志
    is_used_in_digest = Column(Boolean, default=False)  # 是否已被纳入快报
    is_processed = Column(Boolean, default=False)  # 是否已被AI处理

    # 元数据
    publish_date = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关联
    source = relationship("Source")
