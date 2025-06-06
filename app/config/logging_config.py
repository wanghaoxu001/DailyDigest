import logging
import logging.handlers
import os
import sys
import threading
import io
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import json


class JsonFormatter(logging.Formatter):
    """JSON格式化器，用于结构化日志"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # 添加异常信息
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        # 添加额外的字段
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
            
        return json.dumps(log_entry, ensure_ascii=False)


class CustomLogRecord(logging.LogRecord):
    """自定义日志记录，支持额外字段"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_fields = {}


class ContextFilter(logging.Filter):
    """上下文过滤器，添加请求ID等上下文信息"""
    
    def filter(self, record):
        # 可以在这里添加请求ID、用户ID等上下文信息
        record.request_id = getattr(record, 'request_id', 'N/A')
        return True


class LogManager:
    """日志管理器"""
    
    def __init__(self):
        self.log_buffers: Dict[str, io.StringIO] = {}
        self.log_locks: Dict[str, threading.Lock] = {}
        self.max_buffer_lines = 1000
        self._initialized = False
        
    def setup_logging(self, 
                     log_level: str = "INFO",
                     log_dir: str = "logs",
                     enable_console: bool = True,
                     enable_file: bool = True,
                     enable_json: bool = False,
                     enable_buffer: bool = True,
                     max_bytes: int = 10 * 1024 * 1024,  # 10MB
                     backup_count: int = 5):
        """
        设置统一的日志配置
        
        Args:
            log_level: 日志级别
            log_dir: 日志目录
            enable_console: 是否启用控制台输出
            enable_file: 是否启用文件输出
            enable_json: 是否启用JSON格式
            enable_buffer: 是否启用内存缓冲
            max_bytes: 日志文件最大大小
            backup_count: 备份文件数量
        """
        if self._initialized:
            return
            
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # 获取根日志记录器
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除现有处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
        # 设置格式化器
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s'
        )
        json_formatter = JsonFormatter()
        
        # 控制台处理器
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(console_formatter)
            console_handler.addFilter(ContextFilter())
            root_logger.addHandler(console_handler)
            
        # 文件处理器
        if enable_file:
            # 主日志文件
            file_handler = logging.handlers.RotatingFileHandler(
                log_path / "daily_digest.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(file_formatter)
            file_handler.addFilter(ContextFilter())
            root_logger.addHandler(file_handler)
            
            # 错误日志文件
            error_handler = logging.handlers.RotatingFileHandler(
                log_path / "errors.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(file_formatter)
            error_handler.addFilter(ContextFilter())
            root_logger.addHandler(error_handler)
            
            # 爬虫专用日志文件
            crawler_logger = logging.getLogger('app.services.crawler')
            crawler_handler = logging.handlers.RotatingFileHandler(
                log_path / "crawler.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            crawler_handler.setLevel(logging.DEBUG)
            crawler_handler.setFormatter(file_formatter)
            crawler_logger.addHandler(crawler_handler)
            
            # LLM处理专用日志文件
            llm_logger = logging.getLogger('app.services.llm_processor')
            llm_handler = logging.handlers.RotatingFileHandler(
                log_path / "llm_processor.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            llm_handler.setLevel(logging.DEBUG)
            llm_handler.setFormatter(file_formatter)
            llm_logger.addHandler(llm_handler)
            
        # JSON格式日志
        if enable_json:
            json_handler = logging.handlers.RotatingFileHandler(
                log_path / "daily_digest.json.log",
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            json_handler.setLevel(logging.INFO)
            json_handler.setFormatter(json_formatter)
            json_handler.addFilter(ContextFilter())
            root_logger.addHandler(json_handler)
            
        # 内存缓冲器
        if enable_buffer:
            self._setup_buffer_handlers()
            
        self._initialized = True
        
        # 记录初始化信息
        logger = logging.getLogger(__name__)
        logger.info(f"日志系统初始化完成 - 级别: {log_level}, 目录: {log_dir}")
        logger.info(f"控制台: {enable_console}, 文件: {enable_file}, JSON: {enable_json}, 缓冲: {enable_buffer}")
        
    def _setup_buffer_handlers(self):
        """设置内存缓冲处理器"""
        buffer_names = ['general', 'crawler', 'llm', 'error']
        
        for buffer_name in buffer_names:
            # 创建缓冲区
            buffer = io.StringIO()
            lock = threading.Lock()
            
            self.log_buffers[buffer_name] = buffer
            self.log_locks[buffer_name] = lock
            
            # 创建处理器
            handler = logging.StreamHandler(buffer)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
            handler.setFormatter(formatter)
            
            # 根据缓冲区名称添加到对应的日志记录器
            if buffer_name == 'general':
                logging.getLogger().addHandler(handler)
            elif buffer_name == 'crawler':
                logging.getLogger('app.services.crawler').addHandler(handler)
            elif buffer_name == 'llm':
                logging.getLogger('app.services.llm_processor').addHandler(handler)
            elif buffer_name == 'error':
                handler.setLevel(logging.ERROR)
                logging.getLogger().addHandler(handler)
                
    def get_recent_logs(self, buffer_name: str = 'general', max_lines: Optional[int] = None) -> list:
        """获取最近的日志"""
        if buffer_name not in self.log_buffers:
            return [f"缓冲区 '{buffer_name}' 不存在"]
            
        max_lines = max_lines or self.max_buffer_lines
        
        try:
            with self.log_locks[buffer_name]:
                logs = self.log_buffers[buffer_name].getvalue()
                if not logs or logs.strip() == "":
                    return ["尚无日志记录"]

                log_lines = logs.strip().split("\n")
                if len(log_lines) > max_lines:
                    log_lines = log_lines[-max_lines:]
                    # 清空缓冲区并写入最新日志
                    self.log_buffers[buffer_name].truncate(0)
                    self.log_buffers[buffer_name].seek(0)
                    self.log_buffers[buffer_name].write("\n".join(log_lines))

                return [str(line) for line in log_lines if line]
                
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"获取日志失败: {str(e)}")
            return [f"获取日志失败: {str(e)}"]
            
    def clear_logs(self, buffer_name: str = 'general') -> dict:
        """清空日志缓冲区"""
        if buffer_name not in self.log_buffers:
            return {"status": "error", "message": f"缓冲区 '{buffer_name}' 不存在"}
            
        try:
            with self.log_locks[buffer_name]:
                self.log_buffers[buffer_name].truncate(0)
                self.log_buffers[buffer_name].seek(0)
                
            logger = logging.getLogger(__name__)
            logger.info(f"日志缓冲区 '{buffer_name}' 已清空")
            return {"status": "success", "message": f"日志缓冲区 '{buffer_name}' 已清空"}
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"清空日志失败: {str(e)}")
            return {"status": "error", "message": f"清空日志失败: {str(e)}"}
            
    def get_buffer_list(self) -> list:
        """获取所有缓冲区列表"""
        return list(self.log_buffers.keys())
        
    def get_log_stats(self) -> dict:
        """获取日志统计信息"""
        stats = {}
        for buffer_name, buffer in self.log_buffers.items():
            with self.log_locks[buffer_name]:
                content = buffer.getvalue()
                lines = content.count('\n') if content else 0
                size = len(content.encode('utf-8'))
                
            stats[buffer_name] = {
                'lines': lines,
                'size_bytes': size,
                'size_kb': round(size / 1024, 2)
            }
            
        return stats


# 全局日志管理器实例
log_manager = LogManager()


def setup_logging(**kwargs):
    """设置日志系统的便捷函数"""
    # 从环境变量获取配置
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_dir = os.getenv('LOG_DIR', 'logs')
    
    log_manager.setup_logging(
        log_level=log_level,
        log_dir=log_dir,
        **kwargs
    )


def get_logger(name: str) -> logging.Logger:
    """获取日志记录器的便捷函数"""
    return logging.getLogger(name)


def log_with_context(logger: logging.Logger, level: int, message: str, **context):
    """带上下文的日志记录"""
    record = logger.makeRecord(
        logger.name, level, "", 0, message, (), None
    )
    record.extra_fields = context
    logger.handle(record)


# 装饰器：为函数调用添加日志
def log_function_call(logger: Optional[logging.Logger] = None):
    """函数调用日志装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            func_logger.info(f"调用函数: {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                func_logger.info(f"函数 {func.__name__} 执行成功")
                return result
            except Exception as e:
                func_logger.error(f"函数 {func.__name__} 执行失败: {str(e)}", exc_info=True)
                raise
                
        return wrapper
    return decorator 