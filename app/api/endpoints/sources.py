from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
import logging

from app.db.session import get_db
from app.models.source import Source, SourceType
from app.services.crawler import (
    trigger_source_crawl,
    get_recent_logs,
    clear_logs,
    schedule_all_crawling,
)
from app.config import log_manager

router = APIRouter()


# 请求和响应模型
class SourceBase(BaseModel):
    name: str
    url: str
    type: str  # "rss" 或 "webpage"
    active: bool = True
    fetch_interval: int = 3600
    xpath_config: Optional[str] = None
    use_rss_summary: bool = True  # 是否参考RSS原始摘要，默认为True
    use_newspaper: bool = True  # 是否使用Newspaper4k获取文章内容，默认为True
    max_fetch_days: int = 3  # 最多拉取最近X天的文章，默认3天
    use_description_as_summary: bool = False  # 当没有高质量摘要时，使用description作为备选摘要
    description: Optional[str] = None


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    active: Optional[bool] = None
    fetch_interval: Optional[int] = None
    xpath_config: Optional[str] = None
    use_rss_summary: Optional[bool] = None  # 是否参考RSS原始摘要
    use_newspaper: Optional[bool] = None  # 是否使用Newspaper4k获取文章内容
    max_fetch_days: Optional[int] = None  # 最多拉取最近X天的文章
    use_description_as_summary: Optional[bool] = None  # 当没有高质量摘要时，使用description作为备选摘要
    description: Optional[str] = None


class SourceResponse(SourceBase):
    id: int
    last_fetch: Optional[str] = None
    last_fetch_status: Optional[str] = None
    tokens_used: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    created_at: str
    updated_at: str

    # 在Pydantic v2中使用model_config
    model_config = {"from_attributes": True}


# 日志响应模型
class LogsResponse(BaseModel):
    logs: List[str]
    timestamp: str


# 辅助函数 - 将ORM模型转换为字典
def source_to_dict(source: Source) -> dict:
    """将数据库Source模型转换为适合API响应的字典"""
    return {
        "id": source.id,
        "name": source.name,
        "url": source.url,
        "type": source.type.value,  # 枚举转字符串
        "active": source.active,
        "fetch_interval": source.fetch_interval,
        "xpath_config": source.xpath_config,
        "use_rss_summary": getattr(
            source, "use_rss_summary", True
        ),  # 兼容旧数据，默认为True
        "use_newspaper": getattr(
            source, "use_newspaper", True
        ),  # 兼容旧数据，默认为True
        "max_fetch_days": getattr(
            source, "max_fetch_days", 7
        ),  # 兼容旧数据，默认为7天
        "use_description_as_summary": getattr(
            source, "use_description_as_summary", False
        ),  # 兼容旧数据，默认为False
        "description": source.description,
        "tokens_used": int(getattr(source, "tokens_used", 0)),  # 确保是整数
        "prompt_tokens": int(getattr(source, "prompt_tokens", 0)),  # 确保是整数
        "completion_tokens": int(getattr(source, "completion_tokens", 0)),  # 确保是整数
        "last_fetch": source.last_fetch.isoformat() if source.last_fetch else None,
        "last_fetch_status": source.last_fetch_status,
        "last_fetch_result": source.last_fetch_result,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


# API端点
@router.get("/", response_model=List[SourceResponse])
def get_sources(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    """获取所有新闻源"""
    query = db.query(Source)

    if active_only:
        query = query.filter(Source.active == True)

    sources = query.offset(skip).limit(limit).all()

    # 手动转换ORM模型为字典列表
    return [source_to_dict(source) for source in sources]


# 确保特定路由先定义
@router.get("/logs", response_model=LogsResponse)
def get_logs(buffer_name: str = "crawler"):
    """获取最近的抓取和处理日志"""
    try:
        log_lines = get_recent_logs(buffer_name)

        # 确保log_lines是列表且所有元素都是字符串
        if not isinstance(log_lines, list):
            log_lines = [str(log_lines)]
        else:
            # 二次验证确保所有元素都是字符串
            log_lines = [str(line) if line is not None else "" for line in log_lines]

        return {"logs": log_lines, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        # 发生错误时返回错误信息
        logger = logging.getLogger(__name__)
        logger.error(f"获取日志出错: {str(e)}")
        return {
            "logs": [f"获取日志时发生错误: {str(e)}"],
            "timestamp": datetime.now().isoformat(),
        }


@router.post("/logs/clear", status_code=status.HTTP_200_OK)
def clear_log_buffer(buffer_name: str = "crawler"):
    """清空日志缓冲区"""
    return clear_logs(buffer_name)


@router.get("/logs/buffers")
def get_log_buffers():
    """获取所有日志缓冲区列表"""
    return {"buffers": log_manager.get_buffer_list()}


@router.get("/logs/stats")
def get_log_stats():
    """获取日志统计信息"""
    return log_manager.get_log_stats()


@router.post("/", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(source: SourceCreate, db: Session = Depends(get_db)):
    """创建新的新闻源"""
    # 判断类型
    source_type = None
    if source.type == "rss":
        source_type = SourceType.RSS
    elif source.type == "webpage":
        source_type = SourceType.WEBPAGE
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的新闻源类型"
        )

    # 创建新闻源
    db_source = Source(
        name=source.name,
        url=source.url,
        type=source_type,
        active=source.active,
        fetch_interval=source.fetch_interval,
        xpath_config=source.xpath_config,
        use_rss_summary=source.use_rss_summary,
        use_newspaper=source.use_newspaper,
        max_fetch_days=source.max_fetch_days,
        use_description_as_summary=source.use_description_as_summary,
        description=source.description,
    )

    db.add(db_source)
    db.commit()
    db.refresh(db_source)

    # 手动转换为字典
    return source_to_dict(db_source)


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: int, db: Session = Depends(get_db)):
    """获取指定新闻源的详细信息"""
    db_source = db.query(Source).filter(Source.id == source_id).first()

    if db_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="新闻源不存在"
        )

    # 手动转换为字典
    return source_to_dict(db_source)


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int, source_update: SourceUpdate, db: Session = Depends(get_db)
):
    """更新新闻源信息"""
    db_source = db.query(Source).filter(Source.id == source_id).first()

    if db_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="新闻源不存在"
        )

    # 更新字段
    update_data = source_update.dict(exclude_unset=True)

    # 特殊处理type字段
    if "type" in update_data:
        if update_data["type"] == "rss":
            update_data["type"] = SourceType.RSS
        elif update_data["type"] == "webpage":
            update_data["type"] = SourceType.WEBPAGE
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的新闻源类型"
            )

    # 应用更新
    for key, value in update_data.items():
        setattr(db_source, key, value)

    db.commit()
    db.refresh(db_source)

    # 手动转换为字典
    return source_to_dict(db_source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    """删除新闻源"""
    db_source = db.query(Source).filter(Source.id == source_id).first()

    if db_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="新闻源不存在"
        )

    db.delete(db_source)
    db.commit()

    return {"detail": "新闻源已删除"}


@router.post("/{source_id}/crawl", status_code=status.HTTP_202_ACCEPTED)
def crawl_source(source_id: int, db: Session = Depends(get_db)):
    """手动触发对指定新闻源的抓取"""
    db_source = db.query(Source).filter(Source.id == source_id).first()

    if db_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="新闻源不存在"
        )

    # 触发抓取任务
    result = trigger_source_crawl(source_id)

    # 根据结果状态设置响应
    response = {
        "detail": f"抓取任务状态: {result['status']}",
        "message": result.get("message", ""),
        "task_id": result.get("task_id", ""),
        "count": result.get("count", 0),
        "execution_time": result.get("execution_time", ""),
        "status": result.get("status", "unknown"),
    }

    return response


@router.get("/active/count")
def get_active_sources_count(db: Session = Depends(get_db)):
    """获取活跃新闻源数量"""
    count = db.query(Source).filter(Source.active == True).count()
    return {"count": count}


@router.post("/crawl-all", status_code=status.HTTP_202_ACCEPTED)
def crawl_all_sources():
    """触发所有活跃新闻源的抓取"""
    try:
        # 使用celery任务调度所有抓取
        schedule_all_crawling.apply_async(countdown=1)  # 延迟1秒执行，以便API可以快速响应
        return {"detail": "已调度所有活跃新闻源的抓取任务"}
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"调度所有抓取失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"调度所有抓取失败: {str(e)}",
        )


@router.post("/{source_id}/reset-tokens", response_model=SourceResponse)
def reset_source_tokens(source_id: int, db: Session = Depends(get_db)):
    """重置指定新闻源的token统计"""
    db_source = db.query(Source).filter(Source.id == source_id).first()

    if db_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="新闻源不存在"
        )

    # 重置token统计
    db_source.tokens_used = 0
    db_source.prompt_tokens = 0
    db_source.completion_tokens = 0

    db.commit()
    db.refresh(db_source)

    # 手动转换为字典
    return source_to_dict(db_source)


@router.get("/scheduler/status")
def get_scheduler_status():
    """获取定时任务调度器状态"""
    try:
        from app.services.scheduler import scheduler_service
        status = scheduler_service.get_status()
        return status
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"获取调度器状态失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取调度器状态失败: {str(e)}",
        )


@router.get("/scheduler/history")
def get_scheduler_history(limit: int = 20, task_type: Optional[str] = None):
    """获取定时任务执行历史"""
    try:
        from app.services.scheduler import scheduler_service
        history = scheduler_service.get_execution_history(limit=limit, task_type=task_type)
        return {"history": history}
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"获取执行历史失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取执行历史失败: {str(e)}",
        )


@router.get("/scheduler/task-details/{task_id}")
def get_task_details(task_id: int):
    """获取特定任务的详细信息"""
    try:
        from app.services.scheduler import scheduler_service
        details = scheduler_service.get_task_details(task_id)
        if details is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到指定的任务记录",
            )
        return {"task_details": details}
    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"获取任务详情失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务详情失败: {str(e)}",
        )


@router.get("/scheduler/errors")
def get_scheduler_errors(limit: int = 10):
    """获取定时任务错误历史"""
    try:
        from app.services.scheduler import scheduler_service
        errors = scheduler_service.get_error_history(limit=limit)
        return {"errors": errors}
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"获取错误历史失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取错误历史失败: {str(e)}",
        )


@router.get("/scheduler/statistics")
def get_scheduler_statistics():
    """获取定时任务统计信息"""
    try:
        from app.services.scheduler import scheduler_service
        stats = scheduler_service.get_statistics()
        return stats
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"获取统计信息失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}",
        )


@router.post("/scheduler/crawl-now")
def trigger_crawl_now():
    """立即触发新闻源抓取任务"""
    try:
        from app.services.scheduler import scheduler_service
        result = scheduler_service.run_crawl_sources_now()
        
        if result["status"] == "skipped":
            return {"detail": result["message"], "status": "skipped"}, 409  # Conflict
        else:
            return {"detail": result["message"], "status": "started"}, 202  # Accepted
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"手动触发抓取失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"手动触发抓取失败: {str(e)}",
        )


class EventGroupsRequest(BaseModel):
    use_multiprocess: bool = True


@router.post("/scheduler/event-groups-now")
def trigger_event_groups_now(request: EventGroupsRequest = EventGroupsRequest()):
    """立即触发事件分组生成任务"""
    try:
        from app.services.scheduler import scheduler_service
        result = scheduler_service.run_event_generation_now(use_multiprocess=request.use_multiprocess)
        
        method = "多进程" if request.use_multiprocess else "单进程"
        
        if result["status"] == "skipped":
            return {"detail": f"{result['message']} ({method})", "status": "skipped"}, 409  # Conflict
        else:
            return {"detail": f"{result['message']} ({method})", "status": "started"}, 202  # Accepted
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"手动触发事件分组生成失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"手动触发事件分组生成失败: {str(e)}",
        )


class SchedulerSettings(BaseModel):
    crawl_sources_interval: float = Field(ge=0.25, le=24)  # 0.25小时到24小时
    event_generation_interval: Optional[int] = Field(ge=1, le=24, default=None)  # 1小时到24小时


@router.put("/scheduler/settings", status_code=status.HTTP_200_OK)
def update_scheduler_settings(settings: SchedulerSettings):
    """更新定时任务设置"""
    try:
        from app.services.scheduler import scheduler_service
        
        # 更新新闻源抓取间隔
        scheduler_service.set_crawl_sources_interval(settings.crawl_sources_interval)
        
        # 更新事件生成间隔（如果提供）
        if settings.event_generation_interval is not None:
            scheduler_service.set_event_generation_interval(settings.event_generation_interval)
        
        return {
            "detail": f"已更新定时任务设置",
            "crawl_sources_interval": settings.crawl_sources_interval,
            "event_generation_interval": settings.event_generation_interval
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"更新调度器设置失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新调度器设置失败: {str(e)}",
        )


@router.post("/scheduler/clear-task/{task_type}")
def clear_stuck_task(task_type: str):
    """清理卡住的任务状态"""
    try:
        from app.services.scheduler import scheduler_service
        result = scheduler_service.clear_stuck_task(task_type)
        
        if result["status"] == "not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["message"],
            )
        
        return {"detail": result["message"], "status": result["status"]}
    except HTTPException:
        raise
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"清理任务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清理任务失败: {str(e)}",
        )
