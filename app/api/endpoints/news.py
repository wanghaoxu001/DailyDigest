from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Union, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging

from app.db.session import get_db
from app.models.news import News, NewsCategory
from app.services.llm_processor import process_news
from app.services.news_similarity import similarity_service

router = APIRouter()


# 请求和响应模型
class NewsBase(BaseModel):
    title: str
    summary: str
    generated_title: Optional[str] = None
    generated_summary: Optional[str] = None
    article_summary: Optional[str] = None
    category: Optional[str] = None
    is_used_in_digest: bool = False
    is_processed: bool = False


class NewsResponse(NewsBase):
    id: int
    source_id: int
    original_url: str
    original_language: Optional[str] = None
    entities: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None
    publish_date: Optional[str] = None
    fetched_at: str
    created_at: str

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


class SeparatedNewsResponse(BaseModel):
    """分离的新闻响应 - 今日新文章和与历史相似的文章"""
    fresh_news: NewsListResponse
    similar_to_history: NewsListResponse


# 辅助函数 - 将ORM模型转换为字典
def news_to_dict(news: News) -> dict:
    """将数据库News模型转换为适合API响应的字典"""
    return {
        "id": news.id,
        "source_id": news.source_id,
        "title": news.title,
        "summary": news.summary,
        "original_url": news.original_url,
        "original_language": news.original_language,
        "generated_title": news.generated_title,
        "generated_summary": news.generated_summary,
        "article_summary": news.article_summary,
        "category": news.category.value if news.category else None,
        "entities": news.entities,
        "tokens_usage": news.tokens_usage,
        "is_used_in_digest": news.is_used_in_digest,
        "is_processed": news.is_processed,
        "publish_date": news.publish_date.isoformat() if news.publish_date else None,
        "fetched_at": news.fetched_at.isoformat() if news.fetched_at else None,
        "created_at": news.created_at.isoformat() if news.created_at else None,
    }


# API端点
@router.get("/", response_model=NewsListResponse)
def get_news_list(
    skip: int = 0,
    limit: int = 20,
    source_id: Optional[int] = None,
    category: Optional[str] = None,
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

    # 根据是否启用相似度过滤来决定处理方式
    if enable_similarity_filter:
        # 获取所有符合条件的新闻（不先分页）
        all_items = query.all()
        
        # 过滤掉与已用于快报的新闻相似的文章（同一天的除外）
        filtered_items = similarity_service.filter_similar_to_used_news(all_items, db)
        
        # 重新计算总数
        total = len(filtered_items)
        
        # 应用分页
        paginated_items = filtered_items[skip:skip + limit]
    else:
        # 不进行相似度过滤，直接分页查询，性能更好
        total = query.count()
        paginated_items = query.offset(skip).limit(limit).all()

    # 手动转换ORM对象到字典
    news_dicts = [news_to_dict(news) for news in paginated_items]

    return {"total": total, "items": news_dicts}


@router.get("/recent", response_model=NewsListResponse)
def get_recent_news(
    hours: int = 24,
    skip: Optional[int] = Query(0, description="Skip N items for pagination"),
    limit: int = 100,
    exclude_used: bool = False,
    source_id: Optional[int] = None,
    category: Optional[List[str]] = Query(None, description="Category filters, can specify multiple"),
    db: Session = Depends(get_db),
):
    """获取最近一段时间的新闻，用于生成快报"""
    # 确保skip是有效整数
    try:
        skip = max(0, int(skip))
    except (ValueError, TypeError):
        skip = 0

    current_time = datetime.now()
    start_time = current_time - timedelta(hours=hours)

    query = db.query(News).filter(News.created_at >= start_time)

    if exclude_used:
        query = query.filter(News.is_used_in_digest == False)

    # 应用筛选条件
    if source_id:
        query = query.filter(News.source_id == source_id)

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

    # 获取所有符合条件的新闻（不先分页）
    all_items = query.all()
    
    # 过滤掉与已用于快报的新闻相似的文章（同一天的除外）
    filtered_items = similarity_service.filter_similar_to_used_news(all_items, db)
    
    # 重新计算总数
    total = len(filtered_items)
    
    # 应用分页
    paginated_items = filtered_items[skip:skip + limit]

    # 手动转换ORM对象到字典
    news_dicts = [news_to_dict(news) for news in paginated_items]

    return {"total": total, "items": news_dicts}


@router.get("/recent/grouped", response_model=GroupedNewsListResponse)
def get_recent_news_grouped(
    hours: int = 24,
    skip: Optional[int] = Query(0, description="Skip N items for pagination"),
    limit: int = 100,
    exclude_used: bool = False,
    source_id: Optional[int] = None,
    category: Optional[List[str]] = Query(None, description="Category filters, can specify multiple"),
    db: Session = Depends(get_db),
):
    """
    获取最近一段时间的新闻，按事件分组，用于减少重复阅读
    现在使用预计算的分组，大幅提高响应速度
    """
    skip = max(0, int(skip) if skip else 0)
    
    try:
        # 使用预计算的事件分组（性能优化）
        from app.services.news_similarity_storage import news_similarity_storage_service
        
        groups = news_similarity_storage_service.get_precomputed_groups(
            db=db,
            hours=hours,
            categories=category,
            source_ids=[source_id] if source_id else None,
            exclude_used=exclude_used
        )
        
        # 应用分页到分组
        paginated_groups = groups[skip:skip + limit]
        
        # 转换为响应格式
        response_groups = []
        total_news_count = sum(group['news_count'] for group in groups)
        
        for group in paginated_groups:
            # 转换primary新闻
            primary_dict = news_to_dict(group['primary'])
            
            # 转换related新闻
            related_dicts = [news_to_dict(news) for news in group['related']]
            
            response_group = {
                'id': group['id'],
                'event_label': group['event_label'],
                'news_count': group['news_count'],
                'sources': group['sources'],
                'primary': primary_dict,
                'related': related_dicts,
                'similarity_scores': group['similarity_scores'],
                'entities': group['entities'],  # 已经是dict格式
                'is_standalone': group.get('is_standalone', False)
            }
            
            response_groups.append(response_group)
        
        return {
            'total_groups': len(groups),
            'total_news': total_news_count,
            'groups': response_groups
        }
        
    except Exception as e:
        logger.error(f"获取预计算分组失败，回退到实时计算: {str(e)}")
        
        # 回退到实时计算（保持兼容性）
        current_time = datetime.now()
        start_time = current_time - timedelta(hours=hours)
        query = db.query(News).filter(News.created_at >= start_time)
        
        if exclude_used:
            query = query.filter(News.is_used_in_digest == False)
        if source_id:
            query = query.filter(News.source_id == source_id)
        if category:
            try:
                category_enums = []
                for cat_str in category:
                    for enum_item in NewsCategory:
                        if enum_item.value == cat_str:
                            category_enums.append(enum_item)
                            break
                if category_enums:
                    query = query.filter(News.category.in_(category_enums))
                else:
                    query = query.filter(News.id == -1)
            except Exception:
                query = query.filter(News.id == -1)
        
        all_news = query.order_by(News.created_at.desc()).all()
        
        # 使用简化的分组逻辑（避免实时相似度计算）
        response_groups = []
        total_news_count = len(all_news)
        
        # 将每条新闻作为独立的"组"返回
        paginated_news = all_news[skip:skip + limit]
        for i, news in enumerate(paginated_news):
            response_group = {
                'id': f'standalone_{news.id}',
                'event_label': news.generated_title or news.title,
                'news_count': 1,
                'sources': [str(news.source_id)],
                'primary': news_to_dict(news),
                'related': [],
                'similarity_scores': {},
                'entities': {},
                'is_standalone': True
            }
            response_groups.append(response_group)
        
        return {
            'total_groups': len(response_groups),
            'total_news': total_news_count,
            'groups': response_groups
        }


@router.get("/recent/separated", response_model=SeparatedNewsResponse)
def get_recent_news_separated(
    hours: int = 24,
    skip: Optional[int] = Query(0, description="Skip N items for pagination"),
    limit: int = 100,
    exclude_used: bool = False,
    source_id: Optional[int] = None,
    category: Optional[List[str]] = Query(None, description="Category filters, can specify multiple"),
    db: Session = Depends(get_db),
):
    """获取最近一段时间的新闻，分离显示：今日新文章 vs 与历史快报相似的文章"""
    # 确保skip是有效整数
    try:
        skip = max(0, int(skip))
    except (ValueError, TypeError):
        skip = 0

    current_time = datetime.now()
    start_time = current_time - timedelta(hours=hours)

    query = db.query(News).filter(News.created_at >= start_time)

    if exclude_used:
        query = query.filter(News.is_used_in_digest == False)

    # 应用筛选条件
    if source_id:
        query = query.filter(News.source_id == source_id)

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

    # 获取所有符合条件的新闻
    all_items = query.all()
    
    # 移除实时相似度计算，直接返回所有新闻作为"新文章"
    # 实际的相似度分析已经在定时任务中预计算完成
    fresh_news = all_items
    similar_to_history = []  # 不再实时计算与历史的相似度
    
    # 应用分页到新文章
    fresh_total = len(fresh_news)
    fresh_paginated = fresh_news[skip:skip + limit]
    fresh_dicts = [news_to_dict(news) for news in fresh_paginated]
    
    # 相似历史的文章不分页，全部返回（通常数量较少）
    similar_total = len(similar_to_history)
    similar_dicts = [news_to_dict(news) for news in similar_to_history]

    return {
        "fresh_news": {
            "total": fresh_total,
            "items": fresh_dicts
        },
        "similar_to_history": {
            "total": similar_total,
            "items": similar_dicts
        }
    }


@router.get("/{news_id}", response_model=NewsResponse)
def get_news_detail(news_id: int, db: Session = Depends(get_db)):
    """获取新闻详情"""
    db_news = db.query(News).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    # 手动转换ORM对象到字典
    return news_to_dict(db_news)


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
        return news_to_dict(processed_news)
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

    db_news.is_used_in_digest = True
    db.commit()
    db.refresh(db_news)

    # 手动转换ORM对象到字典
    return news_to_dict(db_news)


@router.put("/{news_id}/mark-unused", response_model=NewsResponse)
def mark_news_as_unused(news_id: int, db: Session = Depends(get_db)):
    """将新闻标记为未用于快报"""
    db_news = db.query(News).filter(News.id == news_id).first()

    if db_news is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻不存在")

    db_news.is_used_in_digest = False
    db.commit()
    db.refresh(db_news)

    # 手动转换ORM对象到字典
    return news_to_dict(db_news)


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
    deleted_count = (
        db.query(News)
        .filter(News.id.in_(request.news_ids))
        .delete(synchronize_session=False)
    )
    db.commit()

    # 返回删除结果
    return {"detail": f"成功删除 {deleted_count} 条新闻"}



