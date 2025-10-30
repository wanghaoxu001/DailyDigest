from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from typing import Dict, Any, Optional

from app.db.base import Base


class TaskExecution(Base):
    """任务执行记录模型"""
    __tablename__ = "task_executions"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String(100), nullable=False, index=True)  # 任务类型: crawl_sources, event_generation, cache_cleanup
    task_id = Column(String(200), nullable=True, index=True)  # 任务ID，用于标识同一批次的任务
    status = Column(String(50), nullable=False, index=True)  # 执行状态: running, success, error, warning, info
    message = Column(Text, nullable=True)  # 执行消息
    details = Column(JSON, nullable=True)  # 详细信息，存储为JSON格式
    
    # 时间记录
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Integer, nullable=True)  # 执行时长（秒）
    
    # 进度记录
    progress_current = Column(Integer, nullable=True)  # 当前进度
    progress_total = Column(Integer, nullable=True)    # 总进度
    progress_percentage = Column(Integer, nullable=True)  # 进度百分比
    
    # 结果统计
    items_processed = Column(Integer, nullable=True)  # 处理的项目数量
    items_success = Column(Integer, nullable=True)    # 成功的项目数量
    items_failed = Column(Integer, nullable=True)     # 失败的项目数量
    
    # 系统信息
    hostname = Column(String(100), nullable=True)     # 执行主机名
    process_id = Column(Integer, nullable=True)       # 进程ID
    
    # 错误信息
    error_type = Column(String(200), nullable=True)   # 错误类型
    error_message = Column(Text, nullable=True)       # 错误消息
    stack_trace = Column(Text, nullable=True)         # 堆栈跟踪
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def __repr__(self):
        return f"<TaskExecution(id={self.id}, type='{self.task_type}', status='{self.status}', start={self.start_time})>"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'task_type': self.task_type,
            'task_id': self.task_id,
            'status': self.status,
            'message': self.message,
            'details': self.details,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration_seconds,
            'progress_current': self.progress_current,
            'progress_total': self.progress_total,
            'progress_percentage': self.progress_percentage,
            'items_processed': self.items_processed,
            'items_success': self.items_success,
            'items_failed': self.items_failed,
            'hostname': self.hostname,
            'process_id': self.process_id,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def create_task_start(cls, db, task_type: str, task_id: str = None, 
                         message: str = None, details: Dict = None) -> 'TaskExecution':
        """创建任务开始记录"""
        import socket
        import os
        
        execution = cls(
            task_type=task_type,
            task_id=task_id or f"{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            status='running',
            message=message or f"开始执行任务: {task_type}",
            details=details or {},
            start_time=datetime.now(),
            hostname=socket.gethostname(),
            process_id=os.getpid()
        )
        
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return execution

    def update_progress(self, db, current: int, total: int, message: str = None):
        """更新任务进度"""
        self.progress_current = current
        self.progress_total = total
        self.progress_percentage = int((current / total) * 100) if total > 0 else 0
        if message:
            self.message = message
        self.updated_at = datetime.now()
        db.commit()

    def complete_task(self, db, status: str = 'success', message: str = None, 
                     details: Dict = None, items_processed: int = None,
                     items_success: int = None, items_failed: int = None):
        """完成任务"""
        self.status = status
        self.end_time = datetime.now()
        
        # 计算执行时长，确保时间有效性
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            # 防止负数时长（如果结束时间早于开始时间，可能是系统时间异常）
            if duration < 0:
                # 如果出现负数时长，记录警告并设置为0
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"检测到异常时长: 开始时间={self.start_time}, 结束时间={self.end_time}, 时长={duration}秒")
                self.duration_seconds = 0
                # 修正结束时间为开始时间
                self.end_time = self.start_time
            else:
                self.duration_seconds = int(duration)
        
        if message:
            self.message = message
        if details:
            if self.details:
                self.details.update(details)
            else:
                self.details = details
        
        if items_processed is not None:
            self.items_processed = items_processed
        if items_success is not None:
            self.items_success = items_success
        if items_failed is not None:
            self.items_failed = items_failed
            
        self.updated_at = datetime.now()
        db.commit()

    def fail_task(self, db, error_message: str, error_type: str = None, 
                 stack_trace: str = None, details: Dict = None):
        """标记任务失败"""
        self.status = 'error'
        self.end_time = datetime.now()
        
        # 计算执行时长，确保时间有效性
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            # 防止负数时长
            if duration < 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"检测到异常时长: 开始时间={self.start_time}, 结束时间={self.end_time}, 时长={duration}秒")
                self.duration_seconds = 0
                # 修正结束时间为开始时间
                self.end_time = self.start_time
            else:
                self.duration_seconds = int(duration)
        
        self.error_message = error_message
        self.error_type = error_type
        self.stack_trace = stack_trace
        
        if details:
            if self.details:
                self.details.update(details)
            else:
                self.details = details
                
        self.updated_at = datetime.now()
        db.commit()

    @classmethod
    def acquire_lock(cls, db, task_type: str, message: str = None, details: Dict = None) -> Optional['TaskExecution']:
        """
        尝试获取任务锁（数据库锁机制）
        如果已有同类型任务在运行，返回None
        否则创建新的运行记录并返回
        """
        # 检查是否有同类型任务正在运行
        running_task = db.query(cls).filter(
            cls.task_type == task_type,
            cls.status == 'running'
        ).first()
        
        if running_task:
            # 已有任务在运行，检查是否是僵尸任务（超过2小时未更新）
            from datetime import timedelta
            timeout_threshold = datetime.now() - timedelta(hours=2)
            
            if running_task.updated_at and running_task.updated_at < timeout_threshold:
                # 僵尸任务，强制完成
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"检测到僵尸任务 {running_task.id}，强制完成")
                
                running_task.status = 'error'
                running_task.end_time = datetime.now()
                running_task.error_message = "任务超时，被后续任务强制终止"
                running_task.error_type = "task_timeout"
                if running_task.start_time:
                    running_task.duration_seconds = int((running_task.end_time - running_task.start_time).total_seconds())
                db.commit()
            else:
                # 正常运行中的任务，返回None表示获取锁失败
                return None
        
        # 创建新任务记录
        return cls.create_task_start(db, task_type, message=message, details=details)

    @classmethod
    def release_lock(cls, db, execution_id: int, status: str = 'success', 
                    message: str = None, details: Dict = None):
        """释放任务锁（更新任务状态为完成）"""
        execution = db.query(cls).filter(cls.id == execution_id).first()
        if execution:
            execution.complete_task(db, status, message, details) 