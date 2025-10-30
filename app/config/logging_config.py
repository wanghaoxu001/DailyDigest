import json
import logging
import logging.config
import logging.handlers
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass
class LogEntry:
    """结构化日志条目，用于环形缓冲与API输出"""

    timestamp: datetime
    level: str
    logger: str
    message: str
    module: str
    function: str
    line: int
    context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: logging.LogRecord) -> "LogEntry":
        context: Dict[str, Any] = {}

        # 兼容 log_with_context 中注入的 extra_fields
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            context.update(extra)

        for attr in ("request_id", "task_id", "source_id", "trace_id"):
            if hasattr(record, attr):
                context.setdefault(attr, getattr(record, attr))

        return cls(
            timestamp=datetime.fromtimestamp(record.created),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
            module=record.module,
            function=record.funcName,
            line=record.lineno,
            context=context,
        )

    def to_text(self) -> str:
        base = (
            f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{self.logger} - {self.level} - {self.message}"
        )
        if self.context:
            ctx = json.dumps(self.context, ensure_ascii=False, sort_keys=True)
            return f"{base} | context={ctx}"
        return base

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
            "module": self.module,
            "function": self.function,
            "line": self.line,
            "text": self.to_text(),
        }
        if self.context:
            payload["context"] = self.context
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        timestamp_value = data.get("timestamp")
        if isinstance(timestamp_value, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp_value)
        elif isinstance(timestamp_value, str):
            try:
                timestamp = datetime.fromisoformat(timestamp_value)
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        return cls(
            timestamp=timestamp,
            level=str(data.get("level", "INFO")).upper(),
            logger=data.get("logger", "external"),
            message=data.get("message", ""),
            module=data.get("module", ""),
            function=data.get("function", ""),
            line=int(data.get("line", 0)),
            context=data.get("context", {}) or {},
        )


class JsonFormatter(logging.Formatter):
    """JSON格式化器，用于结构化日志输出到文件/流"""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        entry = LogEntry.from_record(record)
        return json.dumps(entry.to_dict(), ensure_ascii=False)


class ContextFilter(logging.Filter):
    """用于注入 request_id/trace_id 等上下文字段的过滤器"""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if not hasattr(record, "request_id"):
            record.request_id = "N/A"
        return True


class BusinessLogFilter(logging.Filter):
    """
    业务日志过滤器：只允许业务关键日志通过，排除噪音

    允许通过的日志：
    - 爬虫相关：app.services.crawler
    - LLM处理：app.services.llm_processor
    - 快报生成：app.services.digest_generator
    - 任务执行：scripts.cron_jobs.*
    - 所有错误日志（ERROR及以上）

    排除的日志：
    - 中间件请求日志：app.main 中的"中间件收到请求路径"
    - 健康检查：/health, /api/logs/statistics 等频繁请求
    - 数据库连接池日志（除非是错误）
    - Uvicorn访问日志
    """

    # 业务关键模块（允许通过）
    BUSINESS_LOGGERS = {
        "app.services.crawler",
        "app.services.llm_processor",
        "app.services.digest_generator",
        "app.services.duplicate_detector",
        "app.services.news_similarity",
        "app.services.task_execution_service",
        "app.services.task_scheduler",
        "app.services.crawl_tasks",
        "app.services.event_group_tasks",
        "app.services.cache_cleanup_tasks",
    }

    # 任务脚本前缀（允许通过）
    TASK_PREFIXES = ("scripts.cron_jobs.",)

    # 排除的消息模式（正则匹配）
    EXCLUDE_PATTERNS = [
        r"中间件收到请求路径",
        r"INFO:\s+\d+\.\d+\.\d+\.\d+:\d+\s+-\s+\"(GET|POST|PUT|DELETE)",  # Uvicorn访问日志
        r"Application startup complete",
        r"Started server process",
        r"Waiting for application startup",
    ]

    # 排除的路径（用于过滤健康检查等频繁请求）
    EXCLUDE_PATHS = {
        "/health",
        "/api/logs/statistics",
        "/api/logs/",
        "/api/sources/scheduler/status",
    }

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        import re

        # 1. 所有ERROR及以上级别的日志都通过
        if record.levelno >= logging.ERROR:
            return True

        # 2. 检查是否是业务关键模块
        logger_name = record.name

        # 精确匹配业务模块
        if logger_name in self.BUSINESS_LOGGERS:
            return True

        # 前缀匹配任务脚本
        if any(logger_name.startswith(prefix) for prefix in self.TASK_PREFIXES):
            return True

        # 包含匹配（子模块）
        for business_logger in self.BUSINESS_LOGGERS:
            if logger_name.startswith(business_logger):
                return True

        # 3. 排除特定消息模式
        message = record.getMessage()
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, message):
                return False

        # 4. 排除健康检查等频繁请求
        for path in self.EXCLUDE_PATHS:
            if path in message:
                return False

        # 5. 默认不通过（只允许白名单）
        return False


class RingBufferHandler(logging.Handler):
    """写入 LogManager 环形缓冲的处理器"""

    def __init__(self, manager: "LogManager", buffer_name: str, level: int) -> None:
        super().__init__(level=level)
        self.manager = manager
        self.buffer_name = buffer_name

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        try:
            self.manager.append(self.buffer_name, record)
        except Exception:
            self.handleError(record)


class LogManager:
    """统一的日志缓冲与统计管理器"""

    def __init__(self) -> None:
        self.buffers: Dict[str, Deque[LogEntry]] = {}
        self.buffer_locks: Dict[str, threading.Lock] = {}
        self.max_buffer_lines: int = 1000
        self._configured: bool = False
        self._buffer_specs: Dict[str, Tuple[str, int]] = {}

    # --------------------------- 初始化/配置 ---------------------------
    def setup_logging(
        self,
        *,
        log_level: str = "INFO",
        log_dir: str = "logs",
        enable_console: bool = True,
        enable_file: bool = True,
        enable_json: bool = False,
        enable_buffer: bool = True,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        buffer_limit: int = 1000,
    ) -> None:
        """入口函数，替代旧版 setup_logging"""

        if self._configured:
            return

        self.max_buffer_lines = buffer_limit
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        config = self._build_logging_config(
            log_level=log_level,
            log_dir=log_path,
            enable_console=enable_console,
            enable_file=enable_file,
            enable_json=enable_json,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )

        logging.config.dictConfig(config)

        if enable_buffer:
            self._configure_buffers()

        self._configured = True

        logging.getLogger(__name__).info(
            "日志系统初始化完成",
            extra={
                "extra_fields": {
                    "log_level": log_level,
                    "log_dir": str(log_path),
                    "console": enable_console,
                    "file": enable_file,
                    "json": enable_json,
                    "buffer": enable_buffer,
                }
            },
        )

    # --------------------------- 配置构建 ---------------------------
    def _build_logging_config(
        self,
        *,
        log_level: str,
        log_dir: Path,
        enable_console: bool,
        enable_file: bool,
        enable_json: bool,
        max_bytes: int,
        backup_count: int,
    ) -> Dict[str, Any]:
        """构建 dictConfig 配置"""

        formatters: Dict[str, Any] = {
            "console": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "detailed": {
                "format": (
                    "%(asctime)s - %(name)s - %(levelname)s - "
                    "%(module)s:%(funcName)s:%(lineno)d - %(message)s"
                ),
            },
        }

        if enable_json:
            formatters["json"] = {
                "()": JsonFormatter,
            }

        handlers: Dict[str, Any] = {}

        if enable_console:
            handlers["console"] = {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "console",
                "stream": "ext://sys.stdout",
                "filters": ["context"],
            }

        if enable_file:
            handlers.update(
                {
                    "file_main": {
                        "class": "logging.handlers.RotatingFileHandler",
                        "level": "DEBUG",
                        "formatter": "detailed",
                        "filename": str(log_dir / "daily_digest.log"),
                        "maxBytes": max_bytes,
                        "backupCount": backup_count,
                        "encoding": "utf-8",
                        "filters": ["context"],
                    },
                    "file_errors": {
                        "class": "logging.handlers.RotatingFileHandler",
                        "level": "ERROR",
                        "formatter": "detailed",
                        "filename": str(log_dir / "errors.log"),
                        "maxBytes": max_bytes,
                        "backupCount": backup_count,
                        "encoding": "utf-8",
                        "filters": ["context"],
                    },
                    "file_crawler": {
                        "class": "logging.handlers.RotatingFileHandler",
                        "level": "DEBUG",
                        "formatter": "detailed",
                        "filename": str(log_dir / "crawler.log"),
                        "maxBytes": max_bytes,
                        "backupCount": backup_count,
                        "encoding": "utf-8",
                    },
                    "file_llm": {
                        "class": "logging.handlers.RotatingFileHandler",
                        "level": "DEBUG",
                        "formatter": "detailed",
                        "filename": str(log_dir / "llm_processor.log"),
                        "maxBytes": max_bytes,
                        "backupCount": backup_count,
                        "encoding": "utf-8",
                    },
                }
            )

        if enable_json:
            handlers["file_json"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filename": str(log_dir / "daily_digest.json.log"),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "encoding": "utf-8",
                "filters": ["context"],
            }

        root_handlers: List[str] = []
        if enable_console:
            root_handlers.append("console")
        if enable_file:
            root_handlers.append("file_main")
            root_handlers.append("file_errors")
        if enable_json:
            root_handlers.append("file_json")

        loggers: Dict[str, Any] = {
            "app.services.crawler": {
                "handlers": ["file_crawler"],
                "level": "DEBUG",
                "propagate": True,
            },
            "app.services.llm_processor": {
                "handlers": ["file_llm"],
                "level": "DEBUG",
                "propagate": True,
            },
        }

        filters = {"context": {"()": ContextFilter}}

        return {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": filters,
            "formatters": formatters,
            "handlers": handlers,
            "loggers": loggers,
            "root": {
                "level": log_level.upper(),
                "handlers": root_handlers,
            },
        }

    def _configure_buffers(self) -> None:
        """创建环形缓冲并挂载 handler"""

        buffer_specs = {
            "general": ("", logging.INFO),
            "crawler": ("app.services.crawler", logging.INFO),
            "llm": ("app.services.llm_processor", logging.INFO),
            "error": ("", logging.ERROR),
            "scheduler": ("app.services.scheduler", logging.INFO),
            "api": ("app.api", logging.INFO),
            "database": ("app.db", logging.INFO),
            "digest": ("app.services.digest_generator", logging.INFO),
            "task_crawl_sources": ("scripts.cron_jobs.crawl_sources_job", logging.INFO),
            "task_event_groups": ("scripts.cron_jobs.event_groups_job", logging.INFO),
            "task_cache_cleanup": ("scripts.cron_jobs.cache_cleanup_job", logging.INFO),
            # 新增：业务日志聚合缓冲区（排除中间件和系统日志）
            "business": ("", logging.INFO),  # 特殊处理，后面添加过滤器
        }

        self._buffer_specs = buffer_specs

        for name, (logger_name, level) in buffer_specs.items():
            self.buffers[name] = deque(maxlen=self.max_buffer_lines)
            self.buffer_locks[name] = threading.Lock()

            handler = RingBufferHandler(self, name, level)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)

            # 为 business 缓冲区添加过滤器，排除中间件和健康检查日志
            if name == "business":
                handler.addFilter(BusinessLogFilter())

            if logger_name:
                target_logger = logging.getLogger(logger_name)
            else:
                target_logger = logging.getLogger()

            target_logger.addHandler(handler)

    # --------------------------- 缓冲操作 ---------------------------
    def append(self, buffer_name: str, record: logging.LogRecord) -> None:
        if buffer_name not in self.buffers:
            return

        entry = LogEntry.from_record(record)
        with self.buffer_locks[buffer_name]:
            self.buffers[buffer_name].append(entry)

    def ingest_structured_entry(self, buffer_name: str, entry_data: Dict[str, Any]) -> None:
        if buffer_name not in self.buffers:
            return

        entry = LogEntry.from_dict(entry_data)
        if not entry.message:
            entry.message = entry_data.get("text", "")

        with self.buffer_locks[buffer_name]:
            self.buffers[buffer_name].append(entry)

    def _get_entries(self, buffer_name: str) -> List[LogEntry]:
        if buffer_name not in self.buffers:
            return []
        with self.buffer_locks[buffer_name]:
            return list(self.buffers[buffer_name])

    def get_recent_logs(
        self, buffer_name: str = "general", max_lines: Optional[int] = None, structured: bool = False
    ) -> List[Any]:
        if buffer_name not in self.buffers:
            return [] if structured else [f"缓冲区 '{buffer_name}' 不存在"]

        entries = self._get_entries(buffer_name)
        if max_lines:
            entries = entries[-max_lines:]

        if not entries:
            return [] if structured else ["尚无日志记录"]

        if structured:
            return [entry.to_dict() for entry in entries]
        return [entry.to_text() for entry in entries]

    def clear_logs(self, buffer_name: str = "general") -> Dict[str, Any]:
        if buffer_name not in self.buffers:
            return {"status": "error", "message": f"缓冲区 '{buffer_name}' 不存在"}

        with self.buffer_locks[buffer_name]:
            self.buffers[buffer_name].clear()

        logging.getLogger(__name__).info(f"日志缓冲区 '{buffer_name}' 已清空")
        return {"status": "success", "message": f"日志缓冲区 '{buffer_name}' 已清空"}

    def get_buffer_list(self) -> List[str]:
        return list(self.buffers.keys())

    def get_log_stats(self) -> Dict[str, Dict[str, Any]]:
        stats: Dict[str, Dict[str, Any]] = {}
        for name in self.buffers:
            entries = self._get_entries(name)
            size_bytes = sum(len(entry.message.encode("utf-8")) for entry in entries)
            stats[name] = {
                "lines": len(entries),
                "size_bytes": size_bytes,
                "size_kb": round(size_bytes / 1024, 2),
            }
        return stats

    def search_logs(
        self,
        buffer_name: str = "general",
        *,
        keyword: Optional[str] = None,
        regex_pattern: Optional[str] = None,
        level: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        max_results: int = 1000,
    ) -> List[str]:
        """
        搜索日志条目

        Args:
            buffer_name: 缓冲区名称
            keyword: 关键词搜索（不区分大小写）
            regex_pattern: 正则表达式搜索（带超时保护）
            level: 日志级别过滤
            start_time: 开始时间（包含）
            end_time: 结束时间（包含）
            max_results: 最大返回结果数

        Returns:
            匹配的日志文本列表
        """
        if buffer_name not in self.buffers:
            return [f"缓冲区 '{buffer_name}' 不存在"]

        entries = self._get_entries(buffer_name)
        results: List[str] = []

        # 编译正则表达式（如果提供）
        regex_compiled = None
        if regex_pattern:
            try:
                import re
                regex_compiled = re.compile(regex_pattern)
            except re.error as e:
                return [f"正则表达式错误: {str(e)}"]

        for entry in reversed(entries):  # 倒序，提高最近日志的命中率
            # 时间范围过滤
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue

            # 日志级别过滤
            if level and entry.level != level.upper():
                continue

            # 关键词匹配
            if keyword and keyword.lower() not in entry.message.lower():
                continue

            # 正则表达式匹配（带超时保护）
            if regex_compiled:
                try:
                    # 使用超时保护防止ReDoS攻击
                    import signal

                    def timeout_handler(signum, frame):
                        raise TimeoutError("Regex execution timeout")

                    # 设置1秒超时
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(1)

                    try:
                        if not regex_compiled.search(entry.message):
                            continue
                    finally:
                        # 取消超时
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)

                except (TimeoutError, Exception):
                    # 正则超时或错误，跳过此条目
                    continue

            results.append(entry.to_text())
            if len(results) >= max_results:
                break

        return list(reversed(results))

    def get_log_statistics(self) -> Dict[str, Any]:
        statistics: Dict[str, Any] = {}
        for name in self.buffers:
            entries = self._get_entries(name)
            level_counts = {
                "DEBUG": 0,
                "INFO": 0,
                "WARNING": 0,
                "ERROR": 0,
                "CRITICAL": 0,
            }
            for entry in entries:
                if entry.level in level_counts:
                    level_counts[entry.level] += 1

            statistics[name] = {
                "total_lines": len(entries),
                "level_counts": level_counts,
                "last_timestamp": entries[-1].timestamp.isoformat() if entries else None,
            }
        return statistics

    # --------------------------- 文件读取 ---------------------------
    def get_log_file_list(self, log_dir: str = "logs") -> List[Dict[str, Any]]:
        log_path = Path(log_dir)
        if not log_path.exists():
            return []

        files: List[Dict[str, Any]] = []
        for file_path in log_path.glob("*.log*"):
            stat = file_path.stat()
            files.append(
                {
                    "name": file_path.name,
                    "path": str(file_path),
                    "size_bytes": stat.st_size,
                    "size_kb": round(stat.st_size / 1024, 2),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

        files.sort(key=lambda item: item["modified_time"], reverse=True)
        return files

    def read_log_file(
        self, log_file: str, log_dir: str = "logs", max_lines: Optional[int] = None
    ) -> List[str]:
        log_path = Path(log_dir) / log_file
        if not log_path.exists():
            return [f"日志文件 {log_file} 不存在"]

        with log_path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()

        lines = [line.rstrip("\n") for line in lines]
        if max_lines and len(lines) > max_lines:
            lines = lines[-max_lines:]
        return lines if lines else ["日志文件为空"]


# 全局日志管理器实例
log_manager = LogManager()


def setup_logging(**kwargs: Any) -> None:
    """便捷函数，外部调用时透传参数"""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir = os.getenv("LOG_DIR", "logs")

    params = {
        "log_level": log_level,
        "log_dir": log_dir,
    }
    params.update(kwargs)

    log_manager.setup_logging(**params)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_with_context(logger: logging.Logger, level: int, message: str, **context: Any) -> None:
    record = logger.makeRecord(logger.name, level, "", 0, message, (), None)
    record.extra_fields = context
    logger.handle(record)


def log_function_call(logger: Optional[logging.Logger] = None):
    """函数调用日志装饰器"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            target_logger = logger or logging.getLogger(func.__module__)
            trace_context = {"function": func.__name__}
            log_with_context(target_logger, logging.INFO, "调用函数", **trace_context)

            try:
                result = func(*args, **kwargs)
                log_with_context(target_logger, logging.INFO, "函数执行成功", **trace_context)
                return result
            except Exception as exc:
                log_with_context(
                    target_logger,
                    logging.ERROR,
                    f"函数执行失败: {exc}",
                    **trace_context,
                )
                raise

        return wrapper

    return decorator
