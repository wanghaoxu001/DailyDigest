from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
import os
import io

from app.config import log_manager, get_logger

router = APIRouter()
logger = get_logger(__name__)


# 响应模型
class LogEntryModel(BaseModel):
    timestamp: str
    level: str
    logger: str
    message: str
    module: str
    function: str
    line: int
    text: str
    context: Optional[Dict[str, Any]] = None


class LogsResponse(BaseModel):
    logs: List[str]
    entries: List[LogEntryModel]
    buffer_name: str
    timestamp: str
    total_lines: int


class BufferStatsResponse(BaseModel):
    buffer_name: str
    lines: int
    size_bytes: int
    size_kb: float


class LogIngestRequest(BaseModel):
    buffer_name: str = "task_crawl_sources"
    entries: List[LogEntryModel]


class LogStatsResponse(BaseModel):
    buffers: Dict[str, BufferStatsResponse]
    total_buffers: int
    timestamp: str


# 日志级别切换请求
class LogLevelRequest(BaseModel):
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL


# 日志搜索请求
class LogSearchRequest(BaseModel):
    buffer_name: str = "general"
    keyword: Optional[str] = None
    regex_pattern: Optional[str] = None
    level: Optional[str] = None
    hours_ago: Optional[int] = None
    max_results: int = 1000


@router.get("/", response_model=LogsResponse)
def get_logs(buffer_name: str = "general", max_lines: int = 1000):
    """
    获取指定缓冲区的日志
    
    Args:
        buffer_name: 缓冲区名称 (general, crawler, llm, error)
        max_lines: 最大返回行数
    """
    try:
        entries = log_manager.get_recent_logs(buffer_name, max_lines, structured=True)
        raw_lines = log_manager.get_recent_logs(buffer_name, max_lines, structured=False)

        return LogsResponse(
            logs=raw_lines,
            entries=[LogEntryModel(**entry) for entry in entries],
            buffer_name=buffer_name,
            timestamp=datetime.now().isoformat(),
            total_lines=len(entries)
        )
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志失败: {str(e)}"
        )


@router.post("/clear")
def clear_logs(buffer_name: str = "general"):
    """
    清空指定缓冲区的日志
    
    Args:
        buffer_name: 缓冲区名称
    """
    try:
        result = log_manager.clear_logs(buffer_name)
        if result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        return result
    except Exception as e:
        logger.error(f"清空日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空日志失败: {str(e)}"
        )


@router.get("/buffers")
def get_log_buffers():
    """获取所有可用的日志缓冲区列表"""
    try:
        buffers = log_manager.get_buffer_list()
        return {
            "buffers": buffers,
            "count": len(buffers),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取缓冲区列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取缓冲区列表失败: {str(e)}"
        )


@router.get("/stats", response_model=LogStatsResponse)
def get_log_stats():
    """获取所有日志缓冲区的统计信息"""
    try:
        stats = log_manager.get_log_stats()
        
        formatted_stats = {}
        for buffer_name, buffer_stats in stats.items():
            formatted_stats[buffer_name] = BufferStatsResponse(
                buffer_name=buffer_name,
                lines=buffer_stats["lines"],
                size_bytes=buffer_stats["size_bytes"],
                size_kb=buffer_stats["size_kb"]
            )
        
        return LogStatsResponse(
            buffers=formatted_stats,
            total_buffers=len(formatted_stats),
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"获取日志统计失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志统计失败: {str(e)}"
        )


@router.post("/level")
def set_log_level(request: LogLevelRequest):
    """
    动态调整日志级别
    
    Args:
        request: 包含新日志级别的请求
    """
    try:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        level = request.level.upper()
        
        if level not in valid_levels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的日志级别: {level}，有效值: {valid_levels}"
            )
        
        # 设置根日志记录器的级别
        logging.getLogger().setLevel(getattr(logging, level))
        
        logger.info(f"日志级别已调整为: {level}")
        
        return {
            "status": "success",
            "message": f"日志级别已设置为: {level}",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"设置日志级别失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"设置日志级别失败: {str(e)}"
        )


@router.get("/level")
def get_current_log_level():
    """获取当前日志级别"""
    try:
        current_level = logging.getLogger().getEffectiveLevel()
        level_name = logging.getLevelName(current_level)
        
        return {
            "level": level_name,
            "level_number": current_level,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取日志级别失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志级别失败: {str(e)}"
        )


@router.get("/recent/{buffer_name}")
def get_recent_logs_by_buffer(buffer_name: str, lines: int = 100):
    """
    获取指定缓冲区的最近N行日志
    
    Args:
        buffer_name: 缓冲区名称
        lines: 返回的行数
    """
    try:
        if lines > 5000:  # 防止返回过多数据
            lines = 5000
            
        entries = log_manager.get_recent_logs(buffer_name, lines, structured=True)
        log_lines = log_manager.get_recent_logs(buffer_name, lines, structured=False)

        return {
            "logs": log_lines,
            "entries": entries,
            "buffer_name": buffer_name,
            "requested_lines": lines,
            "actual_lines": len(entries),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取最近日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取最近日志失败: {str(e)}"
        )


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
def ingest_logs(request: LogIngestRequest):
    """接收外部结构化日志并写入指定缓冲区"""

    try:
        ingested = 0
        for entry in request.entries:
            log_manager.ingest_structured_entry(request.buffer_name, entry.dict())
            ingested += 1

        return {
            "status": "success",
            "buffer_name": request.buffer_name,
            "ingested": ingested,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"接收外部日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"接收外部日志失败: {str(e)}"
        )


@router.get("/search")
def search_logs(
    buffer_name: str = "general",
    keyword: Optional[str] = None,
    regex_pattern: Optional[str] = None,
    level: Optional[str] = None,
    hours_ago: Optional[int] = None,
    max_results: int = 1000
):
    """
    搜索日志
    
    Args:
        buffer_name: 缓冲区名称
        keyword: 关键词搜索
        regex_pattern: 正则表达式模式
        level: 日志级别过滤
        hours_ago: 最近N小时的日志
        max_results: 最大返回结果数
    """
    try:
        start_time = None
        end_time = None
        
        if hours_ago:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_ago)
        
        log_lines = log_manager.search_logs(
            buffer_name=buffer_name,
            keyword=keyword,
            regex_pattern=regex_pattern,
            level=level,
            start_time=start_time,
            end_time=end_time,
            max_results=max_results
        )
        
        return {
            "logs": log_lines,
            "buffer_name": buffer_name,
            "search_params": {
                "keyword": keyword,
                "regex_pattern": regex_pattern,
                "level": level,
                "hours_ago": hours_ago
            },
            "result_count": len(log_lines),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"搜索日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索日志失败: {str(e)}"
        )


@router.get("/download/{buffer_name}")
def download_logs(buffer_name: str):
    """
    下载指定缓冲区的日志
    
    Args:
        buffer_name: 缓冲区名称
    """
    try:
        log_lines = log_manager.get_recent_logs(buffer_name, max_lines=None)
        
        if not log_lines or log_lines[0].startswith("缓冲区"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"缓冲区 {buffer_name} 不存在或无日志"
            )
        
        # 生成文件内容
        content = "\n".join(log_lines)
        
        # 创建文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs_{buffer_name}_{timestamp}.txt"
        
        # 返回文件流
        return StreamingResponse(
            io.BytesIO(content.encode('utf-8')),
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载日志失败: {str(e)}"
        )


@router.get("/statistics")
def get_log_statistics():
    """
    获取日志详细统计信息
    """
    try:
        statistics = log_manager.get_log_statistics()
        
        # 计算总计
        total_stats = {
            'total_lines': 0,
            'total_errors': 0,
            'total_warnings': 0,
            'total_size_kb': 0
        }
        
        for buffer_stats in statistics.values():
            total_stats['total_lines'] += buffer_stats.get('total_lines', 0)
            total_stats['total_errors'] += buffer_stats.get('level_counts', {}).get('ERROR', 0)
            total_stats['total_warnings'] += buffer_stats.get('level_counts', {}).get('WARNING', 0)
            total_stats['total_size_kb'] += buffer_stats.get('size_kb', 0)
        
        return {
            "statistics": statistics,
            "total": total_stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取日志统计失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志统计失败: {str(e)}"
        )


@router.get("/files")
def get_log_files(log_dir: str = "logs"):
    """
    获取所有日志文件列表
    
    Args:
        log_dir: 日志目录
    """
    try:
        files = log_manager.get_log_file_list(log_dir)
        
        return {
            "files": files,
            "count": len(files),
            "log_dir": log_dir,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取日志文件列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取日志文件列表失败: {str(e)}"
        )


@router.get("/file/{log_file}")
def get_log_file_content(log_file: str, max_lines: Optional[int] = 1000, log_dir: str = "logs"):
    """
    获取磁盘日志文件内容
    
    Args:
        log_file: 日志文件名
        max_lines: 最大读取行数
        log_dir: 日志目录
    """
    try:
        # 安全检查：防止路径遍历
        if ".." in log_file or "/" in log_file or "\\" in log_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件名"
            )
        
        log_lines = log_manager.read_log_file(log_file, log_dir, max_lines)
        
        return {
            "logs": log_lines,
            "file_name": log_file,
            "line_count": len(log_lines),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取日志文件失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取日志文件失败: {str(e)}"
        )


@router.get("/file/{log_file}/download")
def download_log_file(log_file: str, log_dir: str = "logs"):
    """
    下载磁盘日志文件
    
    Args:
        log_file: 日志文件名
        log_dir: 日志目录
    """
    try:
        # 安全检查：防止路径遍历
        if ".." in log_file or "/" in log_file or "\\" in log_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件名"
            )

        from pathlib import Path
        log_path = Path(log_dir) / log_file

        if not log_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"日志文件 {log_file} 不存在"
            )

        return FileResponse(
            path=str(log_path),
            filename=log_file,
            media_type="text/plain"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载日志文件失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载日志文件失败: {str(e)}"
        )


# ==================== 业务日志专用端点 ====================

class BusinessLogsResponse(BaseModel):
    """业务日志响应模型"""
    logs: List[str]
    entries: List[LogEntryModel]
    categories: Dict[str, int]  # 按业务类别统计
    timestamp: str
    total_lines: int


class BusinessFlowStatus(BaseModel):
    """业务流程状态模型"""
    flow_name: str  # 流程名称：爬取/LLM处理/快报生成
    status: str  # running/completed/error
    progress: Dict[str, Any]  # 进度信息
    recent_logs: List[LogEntryModel]  # 最近日志
    error_count: int
    warning_count: int


@router.get("/business", response_model=BusinessLogsResponse)
def get_business_logs(max_lines: int = 1000):
    """
    获取业务日志（爬取、LLM处理、快报生成）

    自动过滤掉中间件、健康检查等噪音日志，只返回业务关键日志
    """
    try:
        # 从 business 缓冲区获取日志
        entries = log_manager.get_recent_logs("business", max_lines, structured=True)

        # 按业务类别统计
        categories = {
            "crawler": 0,
            "llm": 0,
            "digest": 0,
            "task": 0,
            "error": 0
        }

        for entry in entries:
            logger_name = entry.get("logger", "")
            level = entry.get("level", "")

            if "crawler" in logger_name:
                categories["crawler"] += 1
            elif "llm" in logger_name:
                categories["llm"] += 1
            elif "digest" in logger_name:
                categories["digest"] += 1
            elif "cron_jobs" in logger_name or "task" in logger_name:
                categories["task"] += 1

            if level in ["ERROR", "CRITICAL"]:
                categories["error"] += 1

        # 转换为文本行
        logs = [entry["text"] for entry in entries]

        return BusinessLogsResponse(
            logs=logs,
            entries=entries,
            categories=categories,
            timestamp=datetime.now().isoformat(),
            total_lines=len(entries)
        )
    except Exception as e:
        logger.error(f"获取业务日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取业务日志失败: {str(e)}"
        )


@router.get("/business/flow-status")
def get_business_flow_status():
    """
    获取业务流程状态概览

    返回爬取、LLM处理、快报生成三个业务流程的实时状态
    """
    try:
        from app.models.task_execution import TaskExecution
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            # 获取最近的任务执行记录
            recent_crawl = db.query(TaskExecution).filter(
                TaskExecution.task_type == "crawl_sources"
            ).order_by(TaskExecution.start_time.desc()).first()

            recent_event_groups = db.query(TaskExecution).filter(
                TaskExecution.task_type == "event_groups"
            ).order_by(TaskExecution.start_time.desc()).first()

            # 获取每个流程的最近日志
            crawler_logs = log_manager.get_recent_logs("crawler", 10, structured=True)
            llm_logs = log_manager.get_recent_logs("llm", 10, structured=True)
            digest_logs = log_manager.get_recent_logs("digest", 10, structured=True)

            # 统计错误和警告
            def count_errors_warnings(logs):
                errors = sum(1 for log in logs if log.get("level") == "ERROR")
                warnings = sum(1 for log in logs if log.get("level") == "WARNING")
                return errors, warnings

            crawler_errors, crawler_warnings = count_errors_warnings(crawler_logs)
            llm_errors, llm_warnings = count_errors_warnings(llm_logs)
            digest_errors, digest_warnings = count_errors_warnings(digest_logs)

            flows = [
                BusinessFlowStatus(
                    flow_name="新闻抓取",
                    status=recent_crawl.status if recent_crawl else "unknown",
                    progress={
                        "current": recent_crawl.progress_current if recent_crawl else 0,
                        "total": recent_crawl.progress_total if recent_crawl else 0,
                        "message": recent_crawl.message if recent_crawl else "暂无任务"
                    },
                    recent_logs=crawler_logs[:5],
                    error_count=crawler_errors,
                    warning_count=crawler_warnings
                ),
                BusinessFlowStatus(
                    flow_name="LLM处理",
                    status="monitoring",
                    progress={
                        "message": "实时处理中"
                    },
                    recent_logs=llm_logs[:5],
                    error_count=llm_errors,
                    warning_count=llm_warnings
                ),
                BusinessFlowStatus(
                    flow_name="快报生成",
                    status="monitoring",
                    progress={
                        "message": "待生成"
                    },
                    recent_logs=digest_logs[:5],
                    error_count=digest_errors,
                    warning_count=digest_warnings
                )
            ]

            return {
                "flows": [flow.dict() for flow in flows],
                "timestamp": datetime.now().isoformat()
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"获取业务流程状态失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取业务流程状态失败: {str(e)}"
        )


@router.get("/business/timeline")
def get_business_timeline(hours: int = 24):
    """
    获取业务日志时间线数据（用于趋势图）

    Args:
        hours: 查询最近N小时的数据

    Returns:
        按小时分组的日志统计数据
    """
    try:
        # 获取所有业务日志
        entries = log_manager.get_recent_logs("business", 5000, structured=True)

        # 按小时分组统计
        from collections import defaultdict
        timeline = defaultdict(lambda: {"INFO": 0, "WARNING": 0, "ERROR": 0, "total": 0})

        cutoff_time = datetime.now() - timedelta(hours=hours)

        for entry in entries:
            timestamp_str = entry.get("timestamp", "")
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                if timestamp < cutoff_time:
                    continue

                # 按小时分组
                hour_key = timestamp.strftime("%Y-%m-%d %H:00")
                level = entry.get("level", "INFO")

                timeline[hour_key][level] += 1
                timeline[hour_key]["total"] += 1
            except:
                continue

        # 转换为列表格式
        result = [
            {
                "hour": hour,
                "info": stats["INFO"],
                "warning": stats["WARNING"],
                "error": stats["ERROR"],
                "total": stats["total"]
            }
            for hour, stats in sorted(timeline.items())
        ]

        return {
            "timeline": result,
            "hours": hours,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取业务时间线失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取业务时间线失败: {str(e)}"
        )
 
