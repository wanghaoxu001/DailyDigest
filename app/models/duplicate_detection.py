from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base
import enum


class DuplicateDetectionStatus(enum.Enum):
    CHECKING = "checking"  # 正在检查
    NO_DUPLICATE = "no_duplicate"  # 无重复
    DUPLICATE = "duplicate"  # 发现重复
    ERROR = "error"  # 检查出错


class DuplicateDetectionResult(Base):
    __tablename__ = "duplicate_detection_results"

    id = Column(Integer, primary_key=True, index=True)
    digest_id = Column(Integer, ForeignKey("digests.id"), nullable=False)
    news_id = Column(Integer, ForeignKey("news.id"), nullable=False)

    # 检测状态
    status = Column(String(20), default=DuplicateDetectionStatus.CHECKING.value)

    # 重复检测结果
    duplicate_with_news_id = Column(Integer, ForeignKey("news.id"), nullable=True)
    similarity_score = Column(Float, nullable=True)  # 相似度评分 (0-1)
    llm_reasoning = Column(Text, nullable=True)  # LLM的分析推理过程

    # 时间戳
    checked_at = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 关联关系
    digest = relationship("Digest", back_populates="duplicate_detection_results")
    news = relationship("News", foreign_keys=[news_id], back_populates="duplicate_detection_results")
    duplicate_with_news = relationship("News", foreign_keys=[duplicate_with_news_id])