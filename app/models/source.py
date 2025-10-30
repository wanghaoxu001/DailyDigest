from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum, JSON
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class SourceType(enum.Enum):
    RSS = "rss"
    WEBPAGE = "webpage"


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    type = Column(Enum(SourceType), nullable=False)
    active = Column(Boolean, default=True)
    last_fetch = Column(DateTime, nullable=True)
    last_fetch_status = Column(String(20), nullable=True)  # success, error, skipped
    last_fetch_result = Column(JSON, nullable=True)  # 存储上次抓取的详细结果
    fetch_interval = Column(Integer, default=3600)  # 默认每小时抓取一次，单位秒
    xpath_config = Column(Text, nullable=True)  # 网页抓取的XPath配置
    use_rss_summary = Column(Boolean, default=True)  # 是否参考RSS原始摘要，默认为True
    use_newspaper = Column(
        Boolean, default=True
    )  # 是否使用Newspaper4k获取文章内容，默认为True
    max_fetch_days = Column(Integer, default=3)  # 最多拉取最近X天的文章，默认7天
    use_description_as_summary = Column(Boolean, default=False)  # 当没有高质量摘要时，使用description作为备选摘要
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    tokens_used = Column(Integer, default=0)  # 该源消耗的总token数量
    prompt_tokens = Column(Integer, default=0)  # 该源消耗的输入token数量
    completion_tokens = Column(Integer, default=0)  # 该源消耗的输出token数量
