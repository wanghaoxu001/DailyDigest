import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func

from app.models.task_execution import TaskExecution
from app.models.scheduler_config import SchedulerConfig
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class TaskExecutionService:
    """任务执行记录服务"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_task_start(self, task_type: str, task_id: str = None, 
                         message: str = None, details: Dict = None) -> Optional[TaskExecution]:
        """创建任务开始记录"""
        db = SessionLocal()
        try:
            return TaskExecution.create_task_start(
                db, task_type, task_id, message, details
            )
        except Exception as e:
            self.logger.error(f"创建任务开始记录失败: {e}")
            return None
        finally:
            db.close()
    
    def update_task_progress(self, task_execution_id: int, current: int, 
                           total: int, message: str = None) -> bool:
        """更新任务进度"""
        db = SessionLocal()
        try:
            task_execution = db.query(TaskExecution).filter(
                TaskExecution.id == task_execution_id
            ).first()
            
            if not task_execution:
                self.logger.warning(f"未找到任务执行记录: {task_execution_id}")
                return False
            
            task_execution.update_progress(db, current, total, message)
            return True
            
        except Exception as e:
            self.logger.error(f"更新任务进度失败: {e}")
            return False
        finally:
            db.close()
    
    def complete_task(self, task_execution_id: int, status: str = 'success', 
                     message: str = None, details: Dict = None,
                     items_processed: int = None, items_success: int = None, 
                     items_failed: int = None) -> bool:
        """完成任务"""
        db = SessionLocal()
        try:
            task_execution = db.query(TaskExecution).filter(
                TaskExecution.id == task_execution_id
            ).first()
            
            if not task_execution:
                self.logger.warning(f"未找到任务执行记录: {task_execution_id}")
                return False
            
            task_execution.complete_task(
                db, status, message, details, items_processed, 
                items_success, items_failed
            )
            return True
            
        except Exception as e:
            self.logger.error(f"完成任务记录失败: {e}")
            return False
        finally:
            db.close()
    
    def fail_task(self, task_execution_id: int, error_message: str, 
                 error_type: str = None, stack_trace: str = None, 
                 details: Dict = None) -> bool:
        """标记任务失败"""
        db = SessionLocal()
        try:
            task_execution = db.query(TaskExecution).filter(
                TaskExecution.id == task_execution_id
            ).first()
            
            if not task_execution:
                self.logger.warning(f"未找到任务执行记录: {task_execution_id}")
                return False
            
            task_execution.fail_task(db, error_message, error_type, stack_trace, details)
            return True
            
        except Exception as e:
            self.logger.error(f"标记任务失败记录失败: {e}")
            return False
        finally:
            db.close()
    
    def get_task_executions(self, task_type: str = None, status: str = None, 
                          limit: int = 50, offset: int = 0, 
                          start_date: datetime = None, 
                          end_date: datetime = None) -> List[Dict]:
        """获取任务执行记录"""
        db = SessionLocal()
        try:
            query = db.query(TaskExecution)
            
            # 过滤条件
            if task_type:
                query = query.filter(TaskExecution.task_type == task_type)
            if status:
                query = query.filter(TaskExecution.status == status)
            if start_date:
                query = query.filter(TaskExecution.start_time >= start_date)
            if end_date:
                query = query.filter(TaskExecution.start_time <= end_date)
            
            # 排序和分页
            executions = query.order_by(desc(TaskExecution.start_time))\
                            .offset(offset).limit(limit).all()
            
            return [execution.to_dict() for execution in executions]
            
        except Exception as e:
            self.logger.error(f"获取任务执行记录失败: {e}")
            return []
        finally:
            db.close()
    
    def get_task_execution_by_id(self, task_execution_id: int) -> Optional[Dict]:
        """根据ID获取任务执行记录"""
        db = SessionLocal()
        try:
            execution = db.query(TaskExecution).filter(
                TaskExecution.id == task_execution_id
            ).first()
            
            return execution.to_dict() if execution else None
            
        except Exception as e:
            self.logger.error(f"获取任务执行记录失败: {e}")
            return None
        finally:
            db.close()
    
    def get_running_tasks(self) -> List[Dict]:
        """获取正在运行的任务"""
        db = SessionLocal()
        try:
            running_tasks = db.query(TaskExecution).filter(
                TaskExecution.status == 'running'
            ).order_by(TaskExecution.start_time).all()
            
            return [task.to_dict() for task in running_tasks]
            
        except Exception as e:
            self.logger.error(f"获取运行中任务失败: {e}")
            return []
        finally:
            db.close()
    
    def get_task_statistics(self, days: int = 7) -> Dict[str, Any]:
        """获取任务执行统计信息"""
        db = SessionLocal()
        try:
            since_date = datetime.now() - timedelta(days=days)
            
            # 总体统计
            total_count = db.query(TaskExecution).filter(
                TaskExecution.start_time >= since_date
            ).count()
            
            success_count = db.query(TaskExecution).filter(
                and_(
                    TaskExecution.start_time >= since_date,
                    TaskExecution.status == 'success'
                )
            ).count()
            
            error_count = db.query(TaskExecution).filter(
                and_(
                    TaskExecution.start_time >= since_date,
                    TaskExecution.status == 'error'
                )
            ).count()
            
            running_count = db.query(TaskExecution).filter(
                TaskExecution.status == 'running'
            ).count()
            
            # 按任务类型统计
            from sqlalchemy import case
            task_type_stats = db.query(
                TaskExecution.task_type,
                func.count(TaskExecution.id).label('count'),
                func.sum(
                    case((TaskExecution.status == 'success', 1), else_=0)
                ).label('success_count'),
                func.sum(
                    case((TaskExecution.status == 'error', 1), else_=0)
                ).label('error_count'),
                func.avg(TaskExecution.duration_seconds).label('avg_duration')
            ).filter(
                TaskExecution.start_time >= since_date
            ).group_by(TaskExecution.task_type).all()
            
            # 最近的错误记录
            recent_errors = db.query(TaskExecution).filter(
                and_(
                    TaskExecution.start_time >= since_date,
                    TaskExecution.status == 'error'
                )
            ).order_by(desc(TaskExecution.start_time)).limit(10).all()
            
            return {
                'period_days': days,
                'total_executions': total_count,
                'success_count': success_count,
                'error_count': error_count,
                'running_count': running_count,
                'success_rate': round((success_count / total_count * 100) if total_count > 0 else 0, 2),
                'task_type_statistics': [
                    {
                        'task_type': stat.task_type,
                        'total_count': stat.count,
                        'success_count': stat.success_count or 0,
                        'error_count': stat.error_count or 0,
                        'success_rate': round(((stat.success_count or 0) / stat.count * 100) if stat.count > 0 else 0, 2),
                        'avg_duration_seconds': round(float(stat.avg_duration) if stat.avg_duration else 0, 2)
                    }
                    for stat in task_type_stats
                ],
                'recent_errors': [error.to_dict() for error in recent_errors]
            }
            
        except Exception as e:
            self.logger.error(f"获取任务统计信息失败: {e}")
            return {}
        finally:
            db.close()
    
    def cleanup_old_records(self) -> int:
        """清理过期的任务执行记录"""
        db = SessionLocal()
        try:
            # 从配置中获取保留天数
            retention_days = SchedulerConfig.get_value(
                db, 'task_execution_retention_days', default_value=30, value_type='int'
            )
            
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # 删除过期记录
            deleted_count = db.query(TaskExecution).filter(
                TaskExecution.created_at < cutoff_date
            ).delete()
            
            db.commit()
            
            if deleted_count > 0:
                self.logger.info(f"清理了 {deleted_count} 条过期的任务执行记录")
            
            return deleted_count
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"清理过期任务执行记录失败: {e}")
            return 0
        finally:
            db.close()
    
    def force_complete_running_tasks(self, reason: str = "系统重启") -> int:
        """强制完成所有运行中的任务（系统重启时使用）"""
        db = SessionLocal()
        try:
            running_tasks = db.query(TaskExecution).filter(
                TaskExecution.status == 'running'
            ).all()
            
            completed_count = 0
            for task in running_tasks:
                task.status = 'error'
                task.end_time = datetime.now()
                task.error_message = f"任务被强制终止: {reason}"
                task.error_type = "forced_termination"
                
                # 安全计算执行时长
                if task.start_time and task.end_time:
                    duration = (task.end_time - task.start_time).total_seconds()
                    # 防止负数时长
                    if duration < 0:
                        self.logger.warning(f"任务ID {task.id} 检测到异常时长: 开始时间={task.start_time}, 结束时间={task.end_time}")
                        task.duration_seconds = 0
                        task.end_time = task.start_time
                    else:
                        task.duration_seconds = int(duration)
                else:
                    task.duration_seconds = 0
                
                task.updated_at = datetime.now()
                completed_count += 1
            
            db.commit()
            
            if completed_count > 0:
                self.logger.warning(f"强制完成了 {completed_count} 个运行中的任务: {reason}")
            
            return completed_count
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"强制完成运行中任务失败: {e}")
            return 0
        finally:
            db.close()


# 全局服务实例
task_execution_service = TaskExecutionService() 