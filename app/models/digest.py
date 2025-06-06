from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Table, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

# 快报与新闻多对多关系表
digest_news = Table(
    "digest_news",
    Base.metadata,
    Column("digest_id", Integer, ForeignKey("digests.id"), primary_key=True),
    Column("news_id", Integer, ForeignKey("news.id"), primary_key=True)
)

class Digest(Base):
    __tablename__ = "digests"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    date = Column(DateTime, nullable=False)
    content = Column(Text, nullable=True)  # MD格式的内容
    pdf_path = Column(String(500), nullable=True)
    
    # 关联的新闻
    news_items = relationship("News", secondary=digest_news, backref="digests")
    
    # 分类的新闻计数
    news_counts = Column(JSON, nullable=True)  # 例如: {"financial": 3, "major": 5, ...}
    
    # 元数据
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now()) 