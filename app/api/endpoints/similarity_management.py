"""
相似度管理API端点
用于管理预计算的文章相似关系
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime

from app.db.session import get_db
from app.services.news_similarity_storage import news_similarity_storage_service

router = APIRouter()


@router.post("/compute", summary="手动触发相似度计算")
def compute_similarities(
    hours: int = Query(48, description="计算最近多少小时的新闻"),
    force_recalculate: bool = Query(False, description="是否强制重新计算已存在的记录"),
    use_multiprocess: bool = Query(True, description="是否使用多进程并行计算"),
    db: Session = Depends(get_db)
) -> Dict:
    """
    手动触发相似度计算和存储
    """
    try:
        result = news_similarity_storage_service.compute_and_store_similarities(
            db=db,
            hours=hours,
            force_recalculate=force_recalculate,
            use_multiprocess=use_multiprocess
        )
        return {
            "success": True,
            "message": "相似度计算完成",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"相似度计算失败: {str(e)}")


@router.post("/compute-groups", summary="手动触发事件分组计算")
def compute_event_groups(
    hours: int = Query(48, description="计算最近多少小时的新闻"),
    force_recalculate: bool = Query(False, description="是否强制重新计算已存在的分组"),
    db: Session = Depends(get_db)
) -> Dict:
    """
    手动触发事件分组计算和存储
    """
    try:
        result = news_similarity_storage_service.compute_and_store_event_groups(
            db=db,
            hours=hours,
            force_recalculate=force_recalculate
        )
        return {
            "success": True,
            "message": "事件分组计算完成",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"事件分组计算失败: {str(e)}")


@router.post("/compute-all", summary="手动触发完整计算")
def compute_all(
    hours: int = Query(48, description="计算最近多少小时的新闻"),
    force_recalculate: bool = Query(False, description="是否强制重新计算"),
    use_multiprocess: bool = Query(True, description="是否使用多进程并行计算"),
    db: Session = Depends(get_db)
) -> Dict:
    """
    手动触发完整的相似度和分组计算
    """
    try:
        # 1. 计算相似度
        similarity_result = news_similarity_storage_service.compute_and_store_similarities(
            db=db,
            hours=hours,
            force_recalculate=force_recalculate,
            use_multiprocess=use_multiprocess
        )
        
        # 2. 计算分组
        groups_result = news_similarity_storage_service.compute_and_store_event_groups(
            db=db,
            hours=hours,
            force_recalculate=force_recalculate
        )
        
        return {
            "success": True,
            "message": "完整计算完成",
            "similarity_result": similarity_result,
            "groups_result": groups_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"完整计算失败: {str(e)}")


@router.get("/groups", summary="获取预计算的事件分组")
def get_precomputed_groups(
    hours: int = Query(24, description="获取最近多少小时的分组"),
    categories: Optional[List[str]] = Query(None, description="分类过滤"),
    source_ids: Optional[List[int]] = Query(None, description="新闻源过滤"),
    exclude_used: bool = Query(True, description="是否排除已用于快报的新闻"),
    db: Session = Depends(get_db)
) -> Dict:
    """
    获取预计算的事件分组
    """
    try:
        groups = news_similarity_storage_service.get_precomputed_groups(
            db=db,
            hours=hours,
            categories=categories,
            source_ids=source_ids,
            exclude_used=exclude_used
        )
        
        # 简化返回的分组信息
        simplified_groups = []
        for group in groups:
            simplified_group = {
                'id': group['id'],
                'event_label': group['event_label'],
                'news_count': group['news_count'],
                'sources': group['sources'],
                'primary_news_id': group['primary'].id,
                'related_news_ids': [news.id for news in group['related']],
                'is_standalone': group.get('is_standalone', False),
                'created_at': group.get('created_at'),
                'updated_at': group.get('updated_at')
            }
            simplified_groups.append(simplified_group)
        
        return {
            "total": len(groups),
            "groups": simplified_groups
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分组失败: {str(e)}")


@router.post("/cleanup", summary="清理旧记录")
def cleanup_old_records(
    days: int = Query(7, description="保留最近多少天的记录"),
    db: Session = Depends(get_db)
) -> Dict:
    """
    清理旧的相似度记录和分组
    """
    try:
        deleted_count = news_similarity_storage_service.cleanup_old_similarities(
            db=db,
            days=days
        )
        return {
            "success": True,
            "message": f"清理完成，删除了 {deleted_count} 条记录",
            "deleted_count": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")


@router.get("/statistics", summary="获取相似度统计信息")
def get_similarity_statistics(db: Session = Depends(get_db)) -> Dict:
    """
    获取相似度存储的统计信息
    """
    try:
        from app.models.news_similarity import NewsSimilarity, NewsEventGroup, NewsGroupMembership
        from sqlalchemy import func
        
        # 统计相似度记录
        similarity_count = db.query(func.count(NewsSimilarity.id)).scalar()
        high_similarity_count = db.query(func.count(NewsSimilarity.id)).filter(
            NewsSimilarity.similarity_score >= 0.75
        ).scalar()
        
        # 统计事件分组
        groups_count = db.query(func.count(NewsEventGroup.id)).scalar()
        memberships_count = db.query(func.count(NewsGroupMembership.id)).scalar()
        
        # 统计最近的计算时间
        latest_similarity = db.query(NewsSimilarity).order_by(
            NewsSimilarity.created_at.desc()
        ).first()
        
        latest_group = db.query(NewsEventGroup).order_by(
            NewsEventGroup.updated_at.desc()
        ).first()
        
        return {
            "similarity_records": {
                "total": similarity_count,
                "high_similarity": high_similarity_count,
                "latest_calculation": latest_similarity.created_at.isoformat() if latest_similarity else None
            },
            "event_groups": {
                "total": groups_count,
                "total_memberships": memberships_count,
                "latest_update": latest_group.updated_at.isoformat() if latest_group else None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}") 