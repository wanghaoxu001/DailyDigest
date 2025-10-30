from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.db.session import get_db
from app.models.source import Source, SourceType
from app.services.crawler import (
    trigger_source_crawl,
    get_recent_logs,
    clear_logs,
    schedule_all_crawling,
    get_source_logs,
)
from app.config import log_manager, get_logger

router = APIRouter()

# 模块级logger - 统一在此初始化，避免在函数内重复创建
logger = get_logger(__name__)


def _resolve_project_root() -> str:
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        return env_root
    return str(Path(__file__).resolve().parents[3])


def _resolve_python_executable() -> str:
    return os.getenv("PYTHON_EXECUTABLE") or sys.executable


def _run_background_job(
    script_name: str, env_overrides: Optional[Dict[str, str]] = None
) -> None:
    project_root = _resolve_project_root()
    script_path = os.path.join(project_root, "scripts", "cron_jobs", script_name)

    if not os.path.exists(script_path):
        raise FileNotFoundError(f"未找到脚本: {script_path}")

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    subprocess.Popen(
        [_resolve_python_executable(), script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_root,
        env=env,
    )


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
    last_fetch_result: Optional[Dict] = None
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


# 兼容无尾斜杠路径 /api/sources
@router.get("", response_model=List[SourceResponse])
def get_sources_no_slash(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    return get_sources(skip=skip, limit=limit, active_only=active_only, db=db)


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
        logger.error(f"获取 {buffer_name} 缓冲区日志出错: {str(e)}", exc_info=True)
        return {
            "logs": [f"获取日志时发生错误: {str(e)}"],
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/{source_id}/logs", response_model=LogsResponse)
def get_logs_by_source(source_id: int, db: Session = Depends(get_db)):
    """按源ID过滤最近日志（从内存缓冲'crawler'中筛选相关行）"""
    # 校验源是否存在
    source = db.query(Source).filter(Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="新闻源不存在")

    try:
        # 先从源级专属缓冲取日志
        source_specific = get_source_logs(source_id, max_lines=1000)
        if source_specific:
            return {"logs": source_specific, "timestamp": datetime.now().isoformat()}

        # 回退：从通用crawler缓冲中基于ID和名称匹配
        log_lines = get_recent_logs("crawler")
        if not isinstance(log_lines, list):
            log_lines = [str(log_lines)]
        else:
            log_lines = [str(line) if line is not None else "" for line in log_lines]

        import re
        patterns = [
            re.compile(rf"\\bID[:：]?\\s*{source_id}\\b"),
            re.compile(rf"源\\s*ID\\s*{source_id}"),
            re.compile(rf"\(ID:\\s*{source_id}\)"),
        ]
        name_tokens = [getattr(source, "name", None)]
        name_tokens = [t for t in name_tokens if t]

        def match_line(line: str) -> bool:
            for p in patterns:
                if p.search(line):
                    return True
            for n in name_tokens:
                if n and n in line:
                    return True
            return False

        filtered = [line for line in log_lines if match_line(line)]
        if not filtered:
            filtered = [
                f"未找到与源(ID: {source_id}, 名称: {source.name})匹配的日志，以下为最近日志片段："
            ] + log_lines[-200:]

        return {"logs": filtered[-1000:], "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"按源获取日志出错: {str(e)}", exc_info=True)
        return {
            "logs": [f"按源获取日志时发生错误: {str(e)}"],
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

    try:
        db.add(db_source)
        db.commit()
        db.refresh(db_source)
    except Exception as e:
        db.rollback()
        logger.error(f"创建新闻源失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建新闻源失败: {str(e)}",
        )

    # 手动转换为字典
    return source_to_dict(db_source)


# 兼容无尾斜杠路径 POST /api/sources
@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source_no_slash(source: SourceCreate, db: Session = Depends(get_db)):
    return create_source(source, db)


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
    try:
        for key, value in update_data.items():
            setattr(db_source, key, value)

        db.commit()
        db.refresh(db_source)
    except Exception as e:
        db.rollback()
        logger.error(f"更新新闻源失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新新闻源失败: {str(e)}",
        )

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

    try:
        db.delete(db_source)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"删除新闻源失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除新闻源失败: {str(e)}",
        )

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

    # 根据结果状态设置响应，包含execution_id
    response = {
        "detail": f"抓取任务状态: {result['status']}",
        "message": result.get("message", ""),
        "task_id": result.get("task_id", ""),
        "execution_id": result.get("execution_id", None),  # 添加数据库执行记录ID
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
        logger.error(f"调度所有抓取失败: {str(e)}", exc_info=True)
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
    try:
        db_source.tokens_used = 0
        db_source.prompt_tokens = 0
        db_source.completion_tokens = 0

        db.commit()
        db.refresh(db_source)
    except Exception as e:
        db.rollback()
        logger.error(f"重置token统计失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重置token统计失败: {str(e)}",
        )

    # 手动转换为字典
    return source_to_dict(db_source)


@router.get("/scheduler/status")
def get_scheduler_status():
    """获取定时任务调度器状态（基于cron和TaskExecution）"""
    try:
        from app.services.cron_manager import cron_manager
        from app.services.task_execution_service import task_execution_service
        from datetime import datetime
        
        # 获取cron配置
        cron_configs = cron_manager.get_all_configs()
        
        # 获取运行中的任务
        running_tasks = task_execution_service.get_running_tasks()
        
        # 获取最近的执行记录（每种任务类型最近一条）
        recent_executions = {}
        for task_type in ['crawl_sources', 'event_groups', 'cache_cleanup']:
            executions = task_execution_service.get_task_executions(
                task_type=task_type,
                limit=1
            )
            if executions:
                recent_executions[task_type] = executions[0]
        
        # 验证crontab
        verification = cron_manager.verify_crontab()
        
        return {
            'scheduler_type': 'cron',
            'cron_verified': verification.get('verified', False),
            'cron_configs': cron_configs,
            'running_tasks': running_tasks,
            'recent_executions': recent_executions,
            'server_time': datetime.now().isoformat(),
            'server_timezone': 'CST (UTC+8)'
        }
        
    except Exception as e:
        logger.error(f"获取调度器状态失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取调度器状态失败: {str(e)}",
        )


@router.get("/scheduler/history")
def get_scheduler_history(limit: int = 20, task_type: Optional[str] = None):
    """获取定时任务执行历史"""
    try:
        from app.services.task_execution_service import task_execution_service
        history = task_execution_service.get_execution_history(limit=limit, task_type=task_type)
        return {"history": history}
    except Exception as e:
        logger.error(f"获取执行历史失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取执行历史失败: {str(e)}",
        )


@router.get("/scheduler/task-details/{task_id}")
def get_task_details(task_id: int):
    """获取特定任务的详细信息"""
    try:
        from app.services.task_execution_service import task_execution_service
        details = task_execution_service.get_task_details(task_id)
        if details is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到指定的任务记录",
            )
        return {"task_details": details}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务详情失败: {str(e)}",
        )


@router.get("/scheduler/errors")
def get_scheduler_errors(limit: int = 10):
    """获取定时任务错误历史"""
    try:
        from app.services.task_execution_service import task_execution_service
        errors = task_execution_service.get_error_history(limit=limit)
        return {"errors": errors}
    except Exception as e:
        logger.error(f"获取错误历史失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取错误历史失败: {str(e)}",
        )


@router.get("/scheduler/statistics")
def get_scheduler_statistics():
    """获取定时任务统计信息"""
    try:
        from app.services.task_execution_service import task_execution_service
        stats = task_execution_service.get_statistics()
        return stats
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}",
        )


@router.post("/scheduler/crawl-now")
def trigger_crawl_now(background_tasks: BackgroundTasks):
    """
    立即触发新闻源抓取任务

    使用 FastAPI BackgroundTasks 在主进程中执行，
    替代原有的 subprocess.Popen 方式
    """
    try:
        from app.services.crawl_tasks import execute_crawl_sources_task

        # 先创建一个占位任务记录，获取execution_id
        from app.db.session import SessionLocal
        from app.models.task_execution import TaskExecution

        db = SessionLocal()
        try:
            # 检查是否已有任务在运行
            execution = TaskExecution.acquire_lock(
                db,
                'crawl_sources',
                '手动触发：立即抓取新闻源'
            )

            if not execution:
                return {
                    "status": "running",
                    "detail": "新闻源抓取任务已在运行中，请稍后再试"
                }

            execution_id = execution.id

            # 将任务添加到后台执行队列
            background_tasks.add_task(
                _background_crawl_sources,
                execution_id
            )

            return {
                "status": "started",
                "execution_id": execution_id,
                "detail": "新闻源抓取任务已加入队列"
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"手动触发抓取失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"手动触发抓取失败: {str(e)}",
        )


def _background_crawl_sources(execution_id: int):
    """后台执行抓取任务的包装函数"""
    try:
        from app.services.crawl_tasks import _execute_crawl_logic
        _execute_crawl_logic(execution_id)
    except Exception as e:
        logger.error(f"后台抓取任务执行失败: {e}", exc_info=True)
        # 错误已在 _execute_crawl_logic 中记录到 TaskExecution


class EventGroupsRequest(BaseModel):
    use_multiprocess: bool = True


@router.post("/scheduler/event-groups-now")
def trigger_event_groups_now(background_tasks: BackgroundTasks, request: EventGroupsRequest = EventGroupsRequest()):
    """
    立即触发事件分组生成任务

    使用 FastAPI BackgroundTasks 在主进程中执行
    """
    try:
        from app.services.event_group_tasks import execute_event_groups_task
        from app.db.session import SessionLocal
        from app.models.task_execution import TaskExecution

        method = "多进程" if request.use_multiprocess else "单进程"

        db = SessionLocal()
        try:
            # 检查是否已有任务在运行
            execution = TaskExecution.acquire_lock(
                db,
                'event_groups',
                f'手动触发：事件分组任务（{method}）'
            )

            if not execution:
                return {
                    "status": "running",
                    "detail": "事件分组任务已在运行中，请稍后再试"
                }

            execution_id = execution.id

            # 将任务添加到后台执行队列
            background_tasks.add_task(
                _background_event_groups,
                execution_id,
                request.use_multiprocess
            )

            return {
                "status": "started",
                "execution_id": execution_id,
                "detail": f"事件分组任务已加入队列（{method}计算）"
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"手动触发事件分组生成失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"手动触发事件分组生成失败: {str(e)}",
        )


def _background_event_groups(execution_id: int, use_multiprocess: bool):
    """后台执行事件分组任务的包装函数"""
    try:
        from app.services.event_group_tasks import _execute_event_groups_logic
        _execute_event_groups_logic(execution_id, use_multiprocess)
    except Exception as e:
        logger.error(f"后台事件分组任务执行失败: {e}", exc_info=True)


@router.post("/scheduler/cache-cleanup-now")
def trigger_cache_cleanup_now(background_tasks: BackgroundTasks):
    """
    立即触发缓存清理任务

    使用 FastAPI BackgroundTasks 在主进程中执行
    """
    try:
        from app.services.cache_cleanup_tasks import execute_cache_cleanup_task
        from app.db.session import SessionLocal
        from app.models.task_execution import TaskExecution

        db = SessionLocal()
        try:
            # 检查是否已有任务在运行
            execution = TaskExecution.acquire_lock(
                db,
                'cache_cleanup',
                '手动触发：缓存清理任务'
            )

            if not execution:
                return {
                    "status": "running",
                    "detail": "缓存清理任务已在运行中，请稍后再试"
                }

            execution_id = execution.id

            # 将任务添加到后台执行队列
            background_tasks.add_task(
                _background_cache_cleanup,
                execution_id
            )

            return {
                "status": "started",
                "execution_id": execution_id,
                "detail": "缓存清理任务已加入队列"
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"手动触发缓存清理失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"手动触发缓存清理失败: {str(e)}",
        )


def _background_cache_cleanup(execution_id: int):
    """后台执行缓存清理任务的包装函数"""
    try:
        from app.services.cache_cleanup_tasks import _execute_cache_cleanup_logic
        _execute_cache_cleanup_logic(execution_id)
    except Exception as e:
        logger.error(f"后台缓存清理任务执行失败: {e}", exc_info=True)


# ==================== 新的Cron配置管理端点 ====================

@router.get("/scheduler/cron-configs")
def get_cron_configs():
    """获取所有cron配置"""
    try:
        from app.services.cron_manager import cron_manager
        configs = cron_manager.get_all_configs()
        return {"configs": configs}
    except Exception as e:
        logger.error(f"获取cron配置失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取cron配置失败: {str(e)}",
        )


class CronConfigUpdate(BaseModel):
    cron_expression: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


@router.put("/scheduler/cron-configs/{config_id}")
def update_cron_config(config_id: int, update_data: CronConfigUpdate):
    """更新cron配置"""
    try:
        from app.services.cron_manager import cron_manager
        
        result = cron_manager.update_config(
            config_id,
            cron_expression=update_data.cron_expression,
            enabled=update_data.enabled,
            description=update_data.description
        )
        
        if result['status'] == 'error':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['message']
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新cron配置失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新cron配置失败: {str(e)}",
        )


@router.post("/scheduler/cron-reload")
def reload_crontab():
    """重新加载crontab配置到系统"""
    try:
        from app.services.cron_manager import cron_manager
        result = cron_manager.reload_crontab()
        
        if result['status'] == 'error':
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result['message']
            )
        
        # 同时验证安装
        verification = cron_manager.verify_crontab()
        result['verification'] = verification
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新加载crontab失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新加载crontab失败: {str(e)}",
        )


@router.get("/scheduler/cron-verify")
def verify_crontab():
    """验证crontab是否正确安装"""
    try:
        from app.services.cron_manager import cron_manager
        result = cron_manager.verify_crontab()
        return result
    except Exception as e:
        logger.error(f"验证crontab失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"验证crontab失败: {str(e)}",
        )
