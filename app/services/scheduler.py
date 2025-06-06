import logging
import schedule
import time
import threading
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.event_group_cache import event_group_cache_service
from app.models.news import NewsCategory

logger = logging.getLogger(__name__)


class SchedulerService:
    """定时任务服务"""
    
    def __init__(self):
        self.is_running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.event_generation_interval = 1  # 默认每1小时生成一次事件
        
    def start(self):
        """启动定时任务服务"""
        if self.is_running:
            logger.warning("定时任务服务已经在运行")
            return
            
        self.is_running = True
        
        # 设置定时任务
        self._setup_scheduled_jobs()
        
        # 在后台线程中运行调度器
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("定时任务服务已启动")
        
    def stop(self):
        """停止定时任务服务"""
        self.is_running = False
        
        # 清除所有任务
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
            
        logger.info("定时任务服务已停止")
        
    def _setup_scheduled_jobs(self):
        """设置定时任务"""
        # 清除现有任务
        schedule.clear()
        
        # 事件分组生成任务
        schedule.every(self.event_generation_interval).hours.do(self._generate_event_groups_job)
        
        # 缓存清理任务（每天凌晨2点）
        schedule.every().day.at("02:00").do(self._cleanup_old_cache_job)
        
        logger.info(f"已设置定时任务: 事件生成间隔={self.event_generation_interval}小时")
        
    def _run_scheduler(self):
        """运行调度器"""
        logger.info("定时任务调度器开始运行")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"定时任务执行异常: {str(e)}", exc_info=True)
                time.sleep(60)  # 出错后继续运行
                
        logger.info("定时任务调度器已停止")
        
    def _generate_event_groups_job(self):
        """生成事件分组的定时任务"""
        logger.info("开始执行定时事件分组生成任务")
        
        db = SessionLocal()
        try:
            # 为常用的查询组合预生成缓存
            common_configurations = [
                # 默认配置（最近24小时，所有分类，排除已用）
                {
                    'hours': 24,
                    'categories': ['金融业网络安全事件', '重大网络安全事件', '重大数据泄露事件', '重大漏洞风险提示', '其他'],
                    'source_ids': None,
                    'exclude_used': True
                },
                # 最近48小时
                {
                    'hours': 48,
                    'categories': ['金融业网络安全事件', '重大网络安全事件', '重大数据泄露事件', '重大漏洞风险提示', '其他'],
                    'source_ids': None,
                    'exclude_used': True
                },
                # 包含已用于快报的新闻
                {
                    'hours': 24,
                    'categories': ['金融业网络安全事件', '重大网络安全事件', '重大数据泄露事件', '重大漏洞风险提示', '其他'],
                    'source_ids': None,
                    'exclude_used': False
                }
            ]
            
            for config in common_configurations:
                try:
                    groups = event_group_cache_service.get_or_generate_groups(
                        db=db,
                        hours=config['hours'],
                        categories=config['categories'],
                        source_ids=config['source_ids'],
                        exclude_used=config['exclude_used'],
                        force_refresh=True  # 定时任务强制刷新
                    )
                    
                    logger.info(f"成功预生成事件分组: {len(groups)}个组 (hours={config['hours']}, exclude_used={config['exclude_used']})")
                    
                except Exception as e:
                    logger.error(f"预生成事件分组失败 {config}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"定时事件分组生成任务失败: {str(e)}", exc_info=True)
        finally:
            db.close()
            
        logger.info("定时事件分组生成任务完成")
        
    def _cleanup_old_cache_job(self):
        """清理过期缓存的定时任务"""
        logger.info("开始执行缓存清理任务")
        
        db = SessionLocal()
        try:
            # 清理3天前的缓存记录
            from app.models.event_group import EventGroup
            from datetime import timedelta
            
            cutoff_time = datetime.now() - timedelta(days=3)
            
            deleted_count = db.query(EventGroup).filter(
                EventGroup.created_at < cutoff_time
            ).delete(synchronize_session=False)
            
            db.commit()
            
            logger.info(f"清理了 {deleted_count} 条过期缓存记录")
            
        except Exception as e:
            logger.error(f"缓存清理任务失败: {str(e)}", exc_info=True)
            db.rollback()
        finally:
            db.close()
            
    def set_event_generation_interval(self, hours: int):
        """设置事件生成间隔"""
        if hours < 1 or hours > 24:
            raise ValueError("事件生成间隔必须在1-24小时之间")
            
        self.event_generation_interval = hours
        
        # 重新设置定时任务
        if self.is_running:
            self._setup_scheduled_jobs()
            
        logger.info(f"事件生成间隔已更新为 {hours} 小时")
        
    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            'is_running': self.is_running,
            'event_generation_interval': self.event_generation_interval,
            'scheduled_jobs_count': len(schedule.jobs),
            'next_run_times': [job.next_run for job in schedule.jobs if job.next_run]
        }
        
    def run_event_generation_now(self):
        """立即执行事件生成任务"""
        logger.info("手动触发事件生成任务")
        threading.Thread(target=self._generate_event_groups_job, daemon=True).start()


# 全局调度器实例
scheduler_service = SchedulerService() 