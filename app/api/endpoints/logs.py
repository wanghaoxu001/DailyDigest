from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging

from app.config import log_manager, get_logger

router = APIRouter()
logger = get_logger(__name__)


# 响应模型
class LogsResponse(BaseModel):
    logs: List[str]
    buffer_name: str
    timestamp: str
    total_lines: int


class BufferStatsResponse(BaseModel):
    buffer_name: str
    lines: int
    size_bytes: int
    size_kb: float


class LogStatsResponse(BaseModel):
    buffers: Dict[str, BufferStatsResponse]
    total_buffers: int
    timestamp: str


# 日志级别切换请求
class LogLevelRequest(BaseModel):
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL


@router.get("/", response_model=LogsResponse)
def get_logs(buffer_name: str = "general", max_lines: int = 1000):
    """
    获取指定缓冲区的日志
    
    Args:
        buffer_name: 缓冲区名称 (general, crawler, llm, error)
        max_lines: 最大返回行数
    """
    try:
        log_lines = log_manager.get_recent_logs(buffer_name, max_lines)
        
        return LogsResponse(
            logs=log_lines,
            buffer_name=buffer_name,
            timestamp=datetime.now().isoformat(),
            total_lines=len(log_lines)
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
            
        log_lines = log_manager.get_recent_logs(buffer_name, lines)
        
        return {
            "logs": log_lines,
            "buffer_name": buffer_name,
            "requested_lines": lines,
            "actual_lines": len(log_lines),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"获取最近日志失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取最近日志失败: {str(e)}"
        ) 