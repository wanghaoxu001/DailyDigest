from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Union, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
import pytz

from app.db.session import get_db
from app.models.news import News, NewsCategory
from app.services.llm_processor import process_news
from app.config import get_logger

router = APIRouter()

logger = get_logger(__name__)

# 北京时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def format_datetime_with_tz(dt):
    """将datetime对象格式化为带时区信息的ISO字符串"""
    if dt is None:
        return None
    
    # 如果datetime是naive（没有时区信息），假设它是UTC时间
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # 转换到北京时区
    dt = dt.astimezone(BEIJING_TZ)
    
    return dt.isoformat()


# 请求和响应模型
class NewsBase(BaseModel):
    title: str
    summary: str
    generated_title: Optional[str] = None
    generated_summary: Optional[str] = None
    article_summary: Optional[str] = None
    summary_source: Optional[str] = None
    category: Optional[str] = None
    is_used_in_digest: bool = False
    is_processed: bool = False


class NewsResponse(NewsBase):
    id: int
    source_id: int
    source_name: Optional[str] = None
    original_url: str
    original_language: Optional[str] = None
    entities: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    tokens_usage: Optional[Dict[str, Any]] = None
    publish_date: Optional[str] = None
    fetched_at: str
    created_at: str
    digests: List[Dict[str, Any]] = []

    # 在Pydantic v2中使用model_config
    model_config = {"from_attributes": True}


class NewsListResponse(BaseModel):
    total: int
    items: List[NewsResponse]


class NewsGroupResponse(BaseModel):
    id: str
    event_label: str
    news_count: int
    sources: List[str]
    primary: NewsResponse
    related: List[NewsResponse]
    similarity_scores: Dict[int, float]
    entities: Dict[str, List[str]]
    is_standalone: bool = False


class GroupedNewsListResponse(BaseModel):
    total_groups: int
    total_news: int
    groups: List[NewsGroupResponse]


# 辅助函数 - 将ORM模型转换为字典
def news_to_dict(news: News, db: Session = None) -> dict:
    """将数据库News模型转换为适合API响应的字典"""
    # 获取来源名称
    source_name = None
    if db and news.source_id:
        from app.models.source import Source
        source = db.query(Source).filter(Source.id == news.source_id).first()
        if source:
            source_name = source.name

    # 获取所属快报信息 - 通过SQL查询
    digests_info = []
    if db:
        try:
            from app.models.digest import Digest
            # 直接查询包含此新闻的快报
            digests_query = db.query(Digest).join(
                Digest.news_items
            ).filter(News.id == news.id).all()

            for digest in digests_query:
                digests_info.append({
                    "id": digest.id,
                    "title": digest.title,
                    "date": format_datetime_with_tz(digest.date),
                    "created_at": format_datetime_with_tz(digest.created_at)
                })

            logger.info(f"新闻{news.id}找到{len(digests_info)}个关联快报")
        except Exception as e:
            logger.warning(f"查询新闻{news.id}的快报信息时出错: {e}")
            digests_info = []

    return {
        "id": news.id,
        "source_id": news.source_id,
        "source_name": source_name,
        "title": news.title,
        "summary": news.summary,
        "original_url": news.original_url,
        "original_language": news.original_language,
        "generated_title": news.generated_title,
        "generated_summary": news.generated_summary,
        "article_summary": news.article_summary,
        "summary_source": news.summary_source,
        "category": news.category.value if news.category else None,
        "entities": news.entities,
        "tokens_usage": news.tokens_usage,
        "is_used_in_digest": news.is_used_in_digest,
        "is_processed": news.is_processed,
        "publish_date": format_datetime_with_tz(news.publish_date),
        "fetched_at": format_datetime_with_tz(news.fetched_at),
        "created_at": format_datetime_with_tz(news.created_at),
        "digests": digests_info
    }


# API端点
@router.get("/", response_model=NewsListResponse)
def get_news_list(
    skip: int = 0,
    limit: int = 20,
    source_id: Optional[int] = None,
    exclude_source_id: Optional[List[int]] = Query(None, description="Source IDs to exclude"),
    category: Optional[str] = None,
    keyword: Optional[str] = Query(None, description="关键词，匹配标题/摘要/生成标题/生成摘要"),
    is_processed: Optional[bool] = None,
    is_used_in_digest: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    enable_similarity_filter: bool = Query(False, description="是否启用相似度过滤，管理页面建议设为false"),
    db: Session = Depends(get_db),
):
    """获取新闻列表，支持筛选、分页"""
    # 确保skip是有效的非负整数
    try:
        skip = max(0, int(skip))
    except (ValueError, TypeError):
        skip = 0

    query = db.query(News)

    # 应用筛选条件
    if source_id:
        query = query.filter(News.source_id == source_id)

    # 排除指定的来源
    if exclude_source_id:
        query = query.filter(~News.source_id.in_(exclude_source_id))

    if category:
        # 将字符串转换为对应的枚举值进行比较
        try:
            # 查找匹配的枚举值
            category_enum = None
            for enum_item in NewsCategory:
                if enum_item.value == category:
                    category_enum = enum_item
                    break

            if category_enum:
                query = query.filter(News.category == category_enum)
            else:
                # 如果没有找到匹配的枚举值，返回空结果
                query = query.filter(News.id == -1)  # 不存在的ID，确保返回空结果
        except Exception as e:
            # 如果转换失败，返回空结果
            query = query.filter(News.id == -1)

    # 关键词模糊匹配（标题/摘要/生成标题/生成摘要）
    if keyword is not None and str(keyword).strip() != "":
        kw = f"%{str(keyword).strip()}%"
        query = query.filter(
            or_(
                News.title.ilike(kw),
                News.summary.ilike(kw),
                News.generated_title.ilike(kw),
                News.generated_summary.ilike(kw),
            )
        )

    if is_processed is not None:
        query = query.filter(News.is_processed == is_processed)

    if is_used_in_digest is not None:
        query = query.filter(News.is_used_in_digest == is_used_in_digest)

    if start_date:
        query = query.filter(News.created_at >= start_date)

    if end_date:
        query = query.filter(News.created_at <= end_date)

    # 默认按创建时间倒序排序
    query = query.order_by(News.created_at.desc())

    # 不进行相似度过滤，直接分页查询
    total = query.count()
    paginated_items = query.offset(skip).limit(limit).all()

    # 手动转换ORM对象到字典
    news_dicts = [news_to_dict(news, db) for news in paginated_items]

    return {"total": total, "items": news_dicts}


# 兼容无尾斜杠路径 /api/news
@router.get("", response_model=NewsListResponse)
def get_news_list_no_slash(
    skip: int = 0,
    limit: int = 20,
    source_id: Optional[int] = None,
    exclude_source_id: Optional[List[int]] = Query(None, description="Source IDs to exclude"),
    category: Optional[str] = None,
    keyword: Optional[str] = Query(None, description="关键词，匹配标题/摘要/生成标题/生成摘要"),
    is_processed: Optional[bool] = None,
    is_used_in_digest: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    enable_similarity_filter: bool = Query(False, description="是否启用相似度过滤，管理页面建议设为false"),
    db: Session = Depends(get_db),
):
    return get_news_list(
        skip=skip,
        limit=limit,
        source_id=source_id,
        exclude_source_id=exclude_source_id,
        category=category,
        keyword=keyword,
        is_processed=is_processed,
        is_used_in_digest=is_used_in_digest,
        start_date=start_date,
        end_date=end_date,
        enable_similarity_filter=enable_similarity_filter,
        db=db,
    )


@router.get("/recent", response_model=NewsListResponse)
def get_recent_news(
    hours: int = 24,
    skip: Optional[int] = Query(0, description="Skip N items for pagination"),
    limit: int = 100,
    exclude_used: bool = False,
    source_id: Optional[int] = None,
    exclude_source_id: Optional[List[int]] = Query(None, description="Source IDs to exclude"),
    category: Optional[List[str]] = Query(None, description="Category filters, can specify multiple"),
    since_yesterday_digest: bool = Query(False, description="使用昨天最后一次快报时间作为开始时间"),
    db: Session = Depends(get_db),
):
    """获取最近一段时间的新闻，用于生成快报"""
    # 确保skip是有效整数
    try:
        skip = max(0, int(skip))
    except (ValueError, TypeError):
        skip = 0

    # 获取北京时间的当前时间
    current_time = datetime.now(BEIJING_TZ)
    
    # 根据参数决定开始时间
    if since_yesterday_digest:
        # 获取昨天最后一次快报的时间
        from app.models.digest import Digest
        from datetime import time
        
        # 构建昨天的日期范围（北京时间）
        today = current_time.date()
        yesterday_start_beijing = BEIJING_TZ.localize(datetime.combine(today - timedelta(days=1), time.min))
        yesterday_end_beijing = BEIJING_TZ.localize(datetime.combine(today, time.min))
        
        # 转换为UTC时间进行数据库查询（因为数据库存储的是UTC时间）
        yesterday_start_utc = yesterday_start_beijing.astimezone(pytz.UTC).replace(tzinfo=None)
        yesterday_end_utc = yesterday_end_beijing.astimezone(pytz.UTC).replace(tzinfo=None)
        
        # 查询昨天创建的最后一个快报
        last_digest = (
            db.query(Digest)
            .filter(Digest.created_at >= yesterday_start_utc)
            .filter(Digest.created_at < yesterday_end_utc)
            .order_by(Digest.created_at.desc())
            .first()
        )
        
        if last_digest:
            start_time = last_digest.created_at
        else:
            # 如果昨天没有快报，使用昨天开始时间（UTC）
            start_time = yesterday_start_utc
    else:
        # 对于普通时间范围查询，需要转换为UTC时间与数据库比较
        start_time_beijing = current_time - timedelta(hours=hours)
        start_time = start_time_beijing.astimezone(pytz.UTC).replace(tzinfo=None)

    query = db.query(News).filter(News.created_at >= start_time)

    if exclude_used:
        query = query.filter(News.is_used_in_digest == False)

    # 应用筛选条件
    if source_id:
        query = query.filter(News.source_id == source_id)

    # 排除指定的来源
    if exclude_source_id:
        query = query.filter(~News.source_id.in_(exclude_source_id))

    if category:
        # 处理多个分类筛选
        try:
            # 查找匹配的枚举值列表
            category_enums = []
            for cat_str in category:
                for enum_item in NewsCategory:
                    if enum_item.value == cat_str:
                        category_enums.append(enum_item)
                        break

            if category_enums:
                # 使用IN操作符筛选多个分类
                query = query.filter(News.category.in_(category_enums))
            else:
                # 如果没有找到任何匹配的枚举值，返回空结果
                query = query.filter(News.id == -1)  # 不存在的ID，确保返回空结果
        except Exception as e:
            # 如果转换失败，返回空结果
            query = query.filter(News.id == -1)

    # 默认按创建时间倒序排序
    query = query.order_by(News.created_at.desc())

    # 计算总数
    total = query.count()

    # 应用分页
    paginated_items = query.offset(skip).limit(limit).all()

    # 手动转换ORM对象到字典
    news_dicts = [news_to_dict(news, db) for news in paginated_items]

    return {"total": total, "items": news_dicts}


@router.get("/today/count")
def get_today_news_count(db: Session = Depends(get_db)):
    """获取今日新闻数量"""
    from datetime import datetime, time
    
    # 获取北京时间的今天开始时间，然后转换为UTC与数据库比较
    today_beijing = datetime.now(BEIJING_TZ).date()
    today_start_beijing = BEIJING_TZ.localize(datetime.combine(today_beijing, time.min))
    today_start = today_start_beijing.astimezone(pytz.UTC).replace(tzinfo=None)
    
    count = db.query(News).filter(News.created_at >= today_start).count()
    return {"count": count}


@router.get("/{news_id}", response_model=NewsResponse)
def get_news_detail(news_id: int, db: Session = Depends(get_db)):
    """获取新闻详情"""
    from sqlalchemy.orm import selectinload

    # 预加载关联的快报信息
    db_news = db.query(News).options(selectinload(News.digests)).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    # 手动转换ORM对象到字典
    return news_to_dict(db_news, db)


@router.post("/{news_id}/process", response_model=NewsResponse)
def process_news_item(news_id: int, db: Session = Depends(get_db)):
    """手动触发对指定新闻的AI处理"""
    db_news = db.query(News).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    # 调用AI处理服务
    try:
        processed_news = process_news(db_news, db)
        db.commit()

        # 手动转换ORM对象到字典
        return news_to_dict(processed_news, db)
    except Exception as e:
        db.rollback()
        logging.error(f"处理新闻失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理新闻失败: {str(e)}",
        )


@router.put("/{news_id}/mark-used", response_model=NewsResponse)
def mark_news_as_used(news_id: int, db: Session = Depends(get_db)):
    """将新闻标记为已用于快报"""
    db_news = db.query(News).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    try:
        db_news.is_used_in_digest = True
        db.commit()
        db.refresh(db_news)
    except Exception as e:
        db.rollback()
        logger.error(f"标记新闻为已使用失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"标记新闻为已使用失败: {str(e)}",
        )

    # 手动转换ORM对象到字典
    return news_to_dict(db_news, db)


@router.put("/{news_id}/mark-unused", response_model=NewsResponse)
def mark_news_as_unused(news_id: int, db: Session = Depends(get_db)):
    """将新闻标记为未用于快报"""
    db_news = db.query(News).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    try:
        db_news.is_used_in_digest = False
        db.commit()
        db.refresh(db_news)
    except Exception as e:
        db.rollback()
        logger.error(f"标记新闻为未使用失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"标记新闻为未使用失败: {str(e)}",
        )

    # 手动转换ORM对象到字典
    return news_to_dict(db_news, db)


# 批量操作请求模型
class BatchNewsIds(BaseModel):
    news_ids: List[int]


@router.delete("/batch", status_code=status.HTTP_204_NO_CONTENT)
def batch_delete_news(request: BatchNewsIds, db: Session = Depends(get_db)):
    """批量删除新闻"""
    if not request.news_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请提供要删除的新闻ID列表"
        )

    # 记录日志
    logging.info(f"批量删除新闻，ID列表: {request.news_ids}")

    # 执行批量删除
    try:
        deleted_count = (
            db.query(News)
            .filter(News.id.in_(request.news_ids))
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"批量删除新闻失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量删除新闻失败: {str(e)}",
        )

    # 返回删除结果
    return {"detail": f"成功删除 {deleted_count} 条新闻"}


# 重新分类响应模型
class ReclassifyResponse(BaseModel):
    id: int
    original_category: Optional[str] = None
    new_category: Optional[str] = None
    category_changed: bool = False
    message: str


@router.post("/{news_id}/reclassify", response_model=ReclassifyResponse)
def reclassify_news(news_id: int, db: Session = Depends(get_db)):
    """重新判断新闻分类"""
    db_news = db.query(News).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    # 记录原始分类
    original_category = db_news.category.value if db_news.category else None

    try:
        # 使用现有的分类服务重新判断分类
        from app.services.llm_processor import categorize_news
        
        # 获取新闻内容用于分类
        content_for_classification = db_news.content
        if not content_for_classification and db_news.summary:
            content_for_classification = db_news.summary
            
        if not content_for_classification:
            raise ValueError("无法获取新闻内容进行分类")

        # 调用分类服务
        new_category, tokens_usage = categorize_news(db_news.title, content_for_classification)
        
        # 检查分类是否发生变更
        category_changed = (db_news.category != new_category)
        
        # 更新新闻分类
        db_news.category = new_category
        
        # 更新token使用统计
        if tokens_usage and db_news.tokens_usage:
            if isinstance(db_news.tokens_usage, dict):
                # 如果现有的tokens_usage是字典，合并统计
                current_tokens = db_news.tokens_usage.copy()
                current_tokens['prompt_tokens'] = current_tokens.get('prompt_tokens', 0) + tokens_usage.get('prompt_tokens', 0)
                current_tokens['completion_tokens'] = current_tokens.get('completion_tokens', 0) + tokens_usage.get('completion_tokens', 0)
                current_tokens['total_tokens'] = current_tokens.get('total_tokens', 0) + tokens_usage.get('total_tokens', 0)
                db_news.tokens_usage = current_tokens
            else:
                db_news.tokens_usage = tokens_usage
        elif tokens_usage:
            db_news.tokens_usage = tokens_usage
        
        db.commit()
        db.refresh(db_news)

        # 准备响应
        new_category_str = new_category.value if new_category else None
        message = f"重新分类完成"
        
        if category_changed:
            if original_category and new_category_str:
                message = f"分类已从'{original_category}'更改为'{new_category_str}'"
            elif new_category_str:
                message = f"已设置分类为'{new_category_str}'"
            else:
                message = "已清除分类"
        else:
            message = f"分类未变更，仍为'{new_category_str or '未分类'}'"

        return ReclassifyResponse(
            id=news_id,
            original_category=original_category,
            new_category=new_category_str,
            category_changed=category_changed,
            message=message
        )

    except Exception as e:
        db.rollback()
        logging.error(f"重新分类新闻失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新分类失败: {str(e)}",
        )



