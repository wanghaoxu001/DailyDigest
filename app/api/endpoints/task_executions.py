from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.services.task_execution_service import task_execution_service

router = APIRouter()


@router.get("/task-executions", response_model=List[Dict[str, Any]])
async def get_task_executions(
    task_type: Optional[str] = Query(None, description="任务类型过滤"),
    status: Optional[str] = Query(None, description="状态过滤 (running, success, error, warning)"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数量限制"),
    offset: int = Query(0, ge=0, description="偏移量"),
    start_date: Optional[str] = Query(None, description="开始日期 (ISO格式)"),
    end_date: Optional[str] = Query(None, description="结束日期 (ISO格式)")
):
    """
    获取任务执行记录
    
    - **task_type**: 可选，按任务类型过滤 (crawl_sources, event_groups, cache_cleanup, system)
    - **status**: 可选，按状态过滤 (running, success, error, warning, info)
    - **limit**: 返回记录数量，默认50，最大500
    - **offset**: 分页偏移量，默认0
    - **start_date**: 可选，开始日期过滤 (ISO 8601格式)
    - **end_date**: 可选，结束日期过滤 (ISO 8601格式)
    """
    try:
        # 解析日期参数
        start_dt = None
        end_dt = None
        
        if start_date and isinstance(start_date, str):
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="开始日期格式无效，请使用ISO 8601格式")
        
        if end_date and isinstance(end_date, str):
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail="结束日期格式无效，请使用ISO 8601格式")
        
        # 获取任务执行记录
        executions = task_execution_service.get_task_executions(
            task_type=task_type,
            status=status,
            limit=limit,
            offset=offset,
            start_date=start_dt,
            end_date=end_dt
        )
        
        return executions
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务执行记录失败: {str(e)}")


@router.get("/task-executions/{execution_id}", response_model=Dict[str, Any])
async def get_task_execution_by_id(execution_id: int):
    """
    根据ID获取特定的任务执行记录
    
    - **execution_id**: 任务执行记录ID
    """
    execution = task_execution_service.get_task_execution_by_id(execution_id)
    
    if not execution:
        raise HTTPException(status_code=404, detail="任务执行记录未找到")
    
    return execution


@router.get("/task-executions/running/current", response_model=List[Dict[str, Any]])
async def get_running_tasks():
    """
    获取当前正在运行的任务
    """
    try:
        running_tasks = task_execution_service.get_running_tasks()
        return running_tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取运行中任务失败: {str(e)}")


@router.get("/task-executions/statistics", response_model=Dict[str, Any])
async def get_task_statistics(
    days: int = Query(7, ge=1, le=30, description="统计天数范围")
):
    """
    获取任务执行统计信息
    
    - **days**: 统计的天数范围，默认7天，最大30天
    """
    try:
        stats = task_execution_service.get_task_statistics(days=days)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务统计信息失败: {str(e)}")


@router.get("/task-executions/statistics/summary", response_model=Dict[str, Any])
async def get_task_summary():
    """
    获取任务执行概要统计
    """
    try:
        # 获取不同时间范围的统计
        stats_1d = task_execution_service.get_task_statistics(days=1)
        stats_7d = task_execution_service.get_task_statistics(days=7)
        stats_30d = task_execution_service.get_task_statistics(days=30)
        
        # 获取运行中的任务
        running_tasks = task_execution_service.get_running_tasks()
        
        return {
            "summary": {
                "running_tasks_count": len(running_tasks),
                "running_tasks": [
                    {
                        "task_type": task["task_type"],
                        "start_time": task["start_time"],
                        "message": task["message"]
                    }
                    for task in running_tasks
                ]
            },
            "statistics": {
                "last_24_hours": {
                    "total_executions": stats_1d.get("total_executions", 0),
                    "success_count": stats_1d.get("success_count", 0),
                    "error_count": stats_1d.get("error_count", 0),
                    "success_rate": stats_1d.get("success_rate", 0)
                },
                "last_7_days": {
                    "total_executions": stats_7d.get("total_executions", 0),
                    "success_count": stats_7d.get("success_count", 0),
                    "error_count": stats_7d.get("error_count", 0),
                    "success_rate": stats_7d.get("success_rate", 0)
                },
                "last_30_days": {
                    "total_executions": stats_30d.get("total_executions", 0),
                    "success_count": stats_30d.get("success_count", 0),
                    "error_count": stats_30d.get("error_count", 0),
                    "success_rate": stats_30d.get("success_rate", 0)
                }
            },
            "task_type_statistics": stats_7d.get("task_type_statistics", []),
            "recent_errors": stats_7d.get("recent_errors", [])
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务概要统计失败: {str(e)}")


@router.post("/task-executions/cleanup", response_model=Dict[str, Any])
async def cleanup_old_task_executions():
    """
    清理过期的任务执行记录
    
    根据配置的保留天数清理过期记录
    """
    try:
        deleted_count = task_execution_service.cleanup_old_records()
        
        return {
            "status": "success",
            "message": f"成功清理了 {deleted_count} 条过期的任务执行记录",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理过期记录失败: {str(e)}")


@router.post("/task-executions/force-complete-running", response_model=Dict[str, Any])
async def force_complete_running_tasks(
    reason: str = Query("手动强制完成", description="强制完成的原因")
):
    """
    强制完成所有运行中的任务
    
    - **reason**: 强制完成的原因说明
    """
    try:
        completed_count = task_execution_service.force_complete_running_tasks(reason)
        
        return {
            "status": "success",
            "message": f"成功强制完成了 {completed_count} 个运行中的任务",
            "completed_count": completed_count,
            "reason": reason
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"强制完成运行中任务失败: {str(e)}")


@router.get("/task-executions/errors/recent", response_model=List[Dict[str, Any]])
async def get_recent_errors(
    limit: int = Query(20, ge=1, le=100, description="返回记录数量限制"),
    hours: int = Query(24, ge=1, le=168, description="时间范围（小时）")
):
    """
    获取最近的错误记录
    
    - **limit**: 返回记录数量，默认20，最大100
    - **hours**: 时间范围，默认24小时，最大168小时（7天）
    """
    try:
        start_date = datetime.now() - timedelta(hours=hours)
        
        errors = task_execution_service.get_task_executions(
            status='error',
            limit=limit,
            start_date=start_date
        )
        
        return errors
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取最近错误记录失败: {str(e)}")


@router.get("/task-executions/types", response_model=List[str])
async def get_task_types():
    """
    获取所有可用的任务类型
    """
    return [
        "crawl_sources",      # 新闻源抓取
        "event_groups",       # 事件分组
        "cache_cleanup",      # 缓存清理
        "system",            # 系统事件
        "scheduler",         # 调度器事件
        "config"             # 配置更新
    ]


@router.get("/task-executions/statuses", response_model=List[str])
async def get_task_statuses():
    """
    获取所有可用的任务状态
    """
    return [
        "running",    # 运行中
        "success",    # 成功
        "error",      # 错误
        "warning",    # 警告
        "info"        # 信息
    ] 