import logging
import schedule
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict
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
        
        # 从数据库加载配置，如果失败则使用默认值
        self._load_config_from_database()
        
        # 执行历史记录
        self.execution_history: List[Dict] = []
        
        # 错误记录
        self.error_history: List[Dict] = []
        
        # 当前正在执行的任务状态
        self.current_tasks: Dict[str, Dict] = {}
        
        # 系统启动时清理状态
        self._cleanup_on_startup()
    
    def _load_config_from_database(self):
        """从数据库加载配置"""
        try:
            from app.db.session import SessionLocal
            from app.models.scheduler_config import SchedulerConfig
            
            db = SessionLocal()
            try:
                # 加载调度器间隔配置
                self.crawl_sources_interval = SchedulerConfig.get_value(
                    db, 'crawl_sources_interval', default_value=1.0, value_type='float'
                )
                self.event_generation_interval = SchedulerConfig.get_value(
                    db, 'event_generation_interval', default_value=1, value_type='int'
                )
                
                # 加载其他配置
                self.max_history_records = SchedulerConfig.get_value(
                    db, 'max_execution_history', default_value=100, value_type='int'
                )
                self.max_error_records = SchedulerConfig.get_value(
                    db, 'max_error_history', default_value=50, value_type='int'
                )
                
                logger.info(f"从数据库加载配置: 抓取间隔={self.crawl_sources_interval}h, "
                          f"事件生成间隔={self.event_generation_interval}h")
                
            finally:
                db.close()
                
        except Exception as e:
            # 如果数据库加载失败，使用默认值
            logger.warning(f"从数据库加载配置失败，使用默认值: {e}")
            self.crawl_sources_interval = 1.0
            self.event_generation_interval = 1
            self.max_history_records = 100
            self.max_error_records = 50
    
    def _save_config_to_database(self, key: str, value, value_type: str, description: str = None):
        """保存配置到数据库"""
        try:
            from app.db.session import SessionLocal
            from app.models.scheduler_config import SchedulerConfig
            
            db = SessionLocal()
            try:
                SchedulerConfig.set_value(
                    db, key, value, value_type, description
                )
                logger.info(f"配置已保存到数据库: {key} = {value}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"保存配置到数据库失败: {e}")
            raise
    
    def _cleanup_on_startup(self):
        """系统启动时清理任务状态"""
        logger.info("系统启动，清理前次运行的任务状态...")
        
        # 清理内存中的当前任务状态
        self.current_tasks.clear()
        
        # 检查是否有上次未完成的任务（通过查询数据库）
        self._check_and_cleanup_incomplete_tasks()
        
        logger.info("任务状态清理完成")
        
    def _check_and_cleanup_incomplete_tasks(self):
        """检查并清理未完成的任务"""
        try:
            import os
            import psutil
            
            # 检查是否有之前的任务状态文件
            status_file = "task_status.tmp"
            if os.path.exists(status_file):
                logger.warning("检测到系统异常关闭，存在未完成的任务状态文件")
                
                try:
                    with open(status_file, 'r', encoding='utf-8') as f:
                        import json
                        task_data = json.load(f)
                        
                    if task_data.get('running_tasks'):
                        running_tasks = task_data['running_tasks']
                        logger.warning(f"上次系统关闭时有未完成的任务: {', '.join(running_tasks)}")
                        
                        # 记录清理信息
                        self._add_execution_record("system", "warning", 
                            f"系统重启，清理了上次未完成的任务: {', '.join(running_tasks)}", {
                                'cleanup_tasks': running_tasks,
                                'startup_time': datetime.now().isoformat(),
                                'last_shutdown': task_data.get('last_update', 'unknown')
                            })
                    
                    # 删除状态文件
                    os.remove(status_file)
                    logger.info("已清理任务状态文件")
                    
                except Exception as e:
                    logger.error(f"清理任务状态文件失败: {e}")
                    # 即使解析失败，也删除文件
                    try:
                        os.remove(status_file)
                    except:
                        pass
            else:
                # 正常启动，记录启动事件
                self._add_execution_record("system", "info", 
                    "系统正常启动，初始化调度器服务", {
                        'startup_time': datetime.now().isoformat()
                    })
                
        except Exception as e:
            logger.error(f"检查未完成任务时出错: {e}")
            # 确保系统能正常启动
            self._add_execution_record("system", "warning", 
                f"系统启动时检查任务状态出错: {str(e)}", {
                    'startup_time': datetime.now().isoformat()
                })
    
    def _save_task_status(self):
        """保存当前任务状态到临时文件"""
        try:
            import json
            status_data = {
                'running_tasks': list(self.current_tasks.keys()),
                'last_update': datetime.now().isoformat(),
                'task_details': {
                    task_type: {
                        'message': task_info.get('message', ''),
                        'start_time': task_info.get('start_time', '').isoformat() if hasattr(task_info.get('start_time', ''), 'isoformat') else str(task_info.get('start_time', ''))
                    }
                    for task_type, task_info in self.current_tasks.items()
                }
            }
            
            with open("task_status.tmp", 'w', encoding='utf-8') as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存任务状态失败: {e}")
        
    def _add_execution_record(self, task_type: str, status: str, message: str, details: Dict = None):
        """添加执行记录"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'task_type': task_type,
            'status': status,
            'message': message,
            'details': details or {}
        }
        
        self.execution_history.insert(0, record)
        
        # 保持历史记录数量限制
        if len(self.execution_history) > self.max_history_records:
            self.execution_history = self.execution_history[:self.max_history_records]
            
        # 如果是错误，也添加到错误历史
        if status == 'error':
            self.error_history.insert(0, record)
            if len(self.error_history) > self.max_error_records:
                self.error_history = self.error_history[:self.max_error_records]
        
        # 更新当前任务状态
        if status == 'running':
            self.current_tasks[task_type] = {
                'start_time': datetime.now(),
                'status': 'running',
                'message': message,
                'details': details or {}
            }
            # 保存任务状态
            self._save_task_status()
        elif status in ['success', 'error'] and task_type in self.current_tasks:
            # 只有任务成功完成或出错时才移除当前任务状态
            # warning状态（如跳过）不应该移除正在运行的任务
            del self.current_tasks[task_type]
            # 更新任务状态文件
            self._save_task_status()
    
    def _update_task_progress(self, task_type: str, message: str, details: Dict = None):
        """更新任务进度"""
        if task_type in self.current_tasks:
            self.current_tasks[task_type].update({
                'message': message,
                'details': details or {},
                'last_update': datetime.now()
            })
            logger.info(f"[{task_type}] {message}")
    
    def _update_task_progress_with_percentage(self, task_type: str, message: str, 
                                            current: int, total: int, details: Dict = None):
        """更新任务进度（包含百分比）"""
        if task_type in self.current_tasks:
            percentage = (current / total * 100) if total > 0 else 0
            progress_details = {
                'current': current,
                'total': total,
                'percentage': round(percentage, 1),
                **(details or {})
            }
            
            self.current_tasks[task_type].update({
                'message': message,
                'details': progress_details,
                'last_update': datetime.now()
            })
            logger.info(f"[{task_type}] {message} ({current}/{total}, {percentage:.1f}%)")
        
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
        self._add_execution_record("scheduler", "success", "定时任务服务已启动")
        
    def stop(self):
        """停止定时任务服务"""
        self.is_running = False
        
        # 清除所有任务
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
            
        # 清理任务状态文件（正常关闭）
        try:
            import os
            if os.path.exists("task_status.tmp"):
                os.remove("task_status.tmp")
                logger.info("已清理任务状态文件")
        except Exception as e:
            logger.error(f"清理任务状态文件失败: {e}")
            
        logger.info("定时任务服务已停止")
        self._add_execution_record("scheduler", "success", "定时任务服务已停止")
        
    def _setup_scheduled_jobs(self):
        """设置定时任务"""
        # 清除现有任务
        schedule.clear()
        
        # 事件分组生成任务（定时任务默认使用多进程）
        schedule.every(self.event_generation_interval).hours.do(lambda: self._generate_event_groups_job(use_multiprocess=True))
        
        # 新闻源抓取任务
        schedule.every(self.crawl_sources_interval).hours.do(self._crawl_sources_job)
        
        # 缓存清理任务（每天凌晨2点）
        schedule.every().day.at("02:00").do(self._cleanup_old_cache_job)
        
        logger.info(f"已设置定时任务: 事件生成间隔={self.event_generation_interval}小时, 新闻源抓取间隔={self.crawl_sources_interval}小时")
        self._add_execution_record("scheduler", "success", "定时任务配置已更新", {
            'event_generation_interval': self.event_generation_interval,
            'crawl_sources_interval': self.crawl_sources_interval,
            'total_jobs': len(schedule.jobs)
        })
        
    def _run_scheduler(self):
        """运行调度器"""
        logger.info("定时任务调度器开始运行")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"定时任务执行异常: {str(e)}", exc_info=True)
                self._add_execution_record("scheduler", "error", f"调度器执行异常: {str(e)}")
                time.sleep(60)  # 出错后继续运行
                
        logger.info("定时任务调度器已停止")
        
    def _crawl_sources_job(self):
        """抓取新闻源的定时任务"""
        # 检查是否已有相同任务在运行
        if "crawl_sources" in self.current_tasks:
            logger.warning("新闻源抓取任务已在运行中，跳过定时执行")
            self._add_execution_record("crawl_sources", "warning", "定时任务跳过：任务已在运行中")
            return
            
        start_time = datetime.now()
        logger.info("开始执行定时新闻源抓取任务")
        self._add_execution_record("crawl_sources", "running", "开始执行定时新闻源抓取任务")
        
        try:
            # 在新线程中执行抓取
            self._execute_crawl_sources()
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"定时新闻源抓取任务执行失败: {str(e)}", exc_info=True)
            self._add_execution_record("crawl_sources", "error", f"抓取任务执行失败: {str(e)}", {
                'execution_time': execution_time,
                'error_details': str(e)
            })
            
            # 任务失败，从current_tasks中移除
            if "crawl_sources" in self.current_tasks:
                del self.current_tasks["crawl_sources"]
    
    def _execute_crawl_sources(self):
        """执行新闻源抓取"""
        from app.services.crawler import crawl_source
        
        start_time = datetime.now()
        
        try:
            self._update_task_progress("crawl_sources", "正在获取活跃的新闻源列表...")
            
            # 获取所有活跃的源
            db = SessionLocal()
            try:
                from app.models.source import Source
                active_sources = db.query(Source).filter(Source.active == True).all()
                
                self._update_task_progress("crawl_sources", f"找到 {len(active_sources)} 个活跃新闻源，开始检查抓取状态...")
                
                total_processed = 0
                successful_crawls = 0
                skipped_sources = 0
                
                for i, source in enumerate(active_sources, 1):
                    try:
                        # 检查是否需要抓取
                        current_time = datetime.now()
                        if source.last_fetch:
                            time_since_last_crawl = (current_time - source.last_fetch).total_seconds()
                            if time_since_last_crawl < source.fetch_interval:
                                skipped_sources += 1
                                self._update_task_progress_with_percentage("crawl_sources", 
                                    f"跳过源: {source.name} (未到抓取时间)", 
                                    i, len(active_sources), {
                                        'successful_crawls': successful_crawls,
                                        'skipped_sources': skipped_sources,
                                        'current_source': source.name,
                                        'action': 'skipped'
                                    })
                                continue
                        
                        self._update_task_progress_with_percentage("crawl_sources", 
                            f"正在抓取: {source.name}", 
                            i, len(active_sources), {
                                'successful_crawls': successful_crawls,
                                'skipped_sources': skipped_sources,
                                'current_source': source.name,
                                'action': 'crawling'
                            })
                        
                        # 执行抓取
                        result = crawl_source(source.id)
                        
                        if result.get('status') == 'success':
                            successful_crawls += 1
                            logger.info(f"成功抓取源 '{source.name}': {result.get('message', '')}")
                        else:
                            logger.warning(f"抓取源 '{source.name}' 失败: {result.get('message', '')}")
                        
                        total_processed += 1
                        
                        self._update_task_progress_with_percentage("crawl_sources", 
                            f"完成抓取: {source.name}", 
                            i, len(active_sources), {
                                'successful_crawls': successful_crawls,
                                'skipped_sources': skipped_sources,
                                'current_source': source.name,
                                'action': 'completed'
                            })
                        
                    except Exception as source_error:
                        logger.error(f"抓取源 '{source.name}' 时出错: {str(source_error)}")
                        self._update_task_progress_with_percentage("crawl_sources", 
                            f"抓取失败: {source.name} - {str(source_error)}", 
                            i, len(active_sources), {
                                'successful_crawls': successful_crawls,
                                'skipped_sources': skipped_sources,
                                'current_source': source.name,
                                'action': 'error',
                                'error': str(source_error)
                            })
                        continue
                
                execution_time = (datetime.now() - start_time).total_seconds()
                message = f"抓取任务完成，用时: {execution_time:.2f}秒，处理了 {total_processed} 个源，成功 {successful_crawls} 个，跳过 {skipped_sources} 个"
                
                self._add_execution_record("crawl_sources", "success", message, {
                    'execution_time': execution_time,
                    'total_sources': len(active_sources),
                    'processed_sources': total_processed,
                    'successful_crawls': successful_crawls,
                    'skipped_sources': skipped_sources
                })
                
                # 任务完成，从current_tasks中移除
                if "crawl_sources" in self.current_tasks:
                    del self.current_tasks["crawl_sources"]
                
            finally:
                db.close()
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"定时新闻源抓取任务执行失败: {str(e)}", exc_info=True)
            self._add_execution_record("crawl_sources", "error", f"抓取任务执行失败: {str(e)}", {
                'execution_time': execution_time,
                'error_details': str(e)
            })
        
    def _generate_event_groups_job(self, is_manual_trigger=False, use_multiprocess=True):
        """生成事件分组的定时任务 - 改为计算并存储相似度和分组"""
        # 只有定时触发时才检查冲突，手动触发时跳过检查（因为在run_event_generation_now中已检查）
        if not is_manual_trigger and "event_groups" in self.current_tasks:
            logger.warning("事件分组任务已在运行中，跳过定时执行")
            self._add_execution_record("event_groups", "warning", "定时任务跳过：任务已在运行中")
            return
            
        start_time = datetime.now()
        logger.info("开始执行定时相似度计算和事件分组任务")
        self._add_execution_record("event_groups", "running", "开始执行相似度计算和事件分组任务")
        
        db = SessionLocal()
        try:
            # 导入新闻相似度存储服务
            from app.services.news_similarity_storage import news_similarity_storage_service
            
            # 1. 计算并存储相似度（最近48小时的新闻）
            self._update_task_progress("event_groups", "正在计算并存储新闻相似度...")
            
            # 定义进度回调函数
            def similarity_progress_callback(message: str, current: int, total: int, details: dict = None):
                self._update_task_progress_with_percentage("event_groups", message, current, total, {
                    'stage': 'similarity_calculation',
                    'stage_details': details or {}
                })
            
            similarity_result = news_similarity_storage_service.compute_and_store_similarities(
                db=db, 
                hours=48, 
                force_recalculate=False,
                progress_callback=similarity_progress_callback,
                use_multiprocess=use_multiprocess  # 使用传入的参数
            )
            
            logger.info(f"相似度计算完成: {similarity_result}")
            self._update_task_progress("event_groups", 
                f"相似度计算完成: 新增 {similarity_result.get('new_similarities', 0)} 条相似度记录")
            
            # 2. 计算并存储事件分组（最近48小时的新闻）
            self._update_task_progress("event_groups", "正在计算并存储事件分组...")
            groups_result = news_similarity_storage_service.compute_and_store_event_groups(
                db=db,
                hours=48,
                force_recalculate=False
            )
            
            logger.info(f"事件分组计算完成: {groups_result}")
            self._update_task_progress("event_groups", 
                f"事件分组计算完成: 创建了 {groups_result.get('groups_created', 0)} 个分组")
            
            # 3. 清理旧的相似度记录（保留7天）
            self._update_task_progress("event_groups", "正在清理旧的相似度记录...")
            cleanup_result = news_similarity_storage_service.cleanup_old_similarities(
                db=db,
                days=7
            )
            
            logger.info(f"清理了 {cleanup_result} 条旧记录")
            self._update_task_progress("event_groups", f"清理了 {cleanup_result} 条旧记录")
            
            # 4. 继续生成事件分组缓存以保持兼容性
            from app.services.event_group_cache import event_group_cache_service
            
            self._update_task_progress("event_groups", "正在生成事件分组缓存...")
            
            cache_total_groups = 0
            common_configurations = [
                {'hours': 24, 'exclude_used': True},
                {'hours': 48, 'exclude_used': True},
                {'hours': 24, 'exclude_used': False}
            ]
            
            for i, config in enumerate(common_configurations, 1):
                try:
                    self._update_task_progress("event_groups", 
                        f"正在生成缓存配置 {i}/{len(common_configurations)} (hours={config['hours']}, exclude_used={config['exclude_used']})...")
                    
                    groups = event_group_cache_service.get_or_generate_groups(
                        db=db,
                        hours=config['hours'],
                        categories=['金融业网络安全事件', '重大网络安全事件', '重大数据泄露事件', '重大漏洞风险提示', '其他'],
                        source_ids=None,
                        exclude_used=config['exclude_used'],
                        force_refresh=True
                    )
                    
                    cache_total_groups += len(groups)
                    logger.info(f"成功预生成事件分组缓存: {len(groups)}个组 (hours={config['hours']}, exclude_used={config['exclude_used']})")
                    
                except Exception as e:
                    logger.error(f"预生成事件分组缓存失败 {config}: {str(e)}")
            
            execution_time = (datetime.now() - start_time).total_seconds()
            message = (
                f"相似度和分组计算完成，用时: {execution_time:.2f}秒，"
                f"新相似度: {similarity_result.get('new_similarities', 0)}条，"
                f"新分组: {groups_result.get('groups_created', 0)}个，"
                f"缓存分组: {cache_total_groups}个，"
                f"清理记录: {cleanup_result}条"
            )
            
            logger.info(message)
            self._add_execution_record("event_groups", "success", message, {
                'execution_time': execution_time,
                'similarity_result': similarity_result,
                'groups_result': groups_result,
                'cache_total_groups': cache_total_groups,
                'cleanup_result': cleanup_result,
                'stage_details': {
                    'similarity_computation': similarity_result,
                    'group_computation': groups_result,
                    'cache_generation': cache_total_groups,
                    'cleanup': cleanup_result
                }
            })
            
            # 任务完成，从current_tasks中移除
            if "event_groups" in self.current_tasks:
                del self.current_tasks["event_groups"]
                    
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_message = f"相似度和分组任务失败: {str(e)}"
            logger.error(f"定时相似度和分组任务失败: {str(e)}", exc_info=True)
            self._add_execution_record("event_groups", "error", error_message, {
                'execution_time': execution_time,
                'error_details': str(e),
                'traceback': str(e.__traceback__) if hasattr(e, '__traceback__') else None
            })
            
            # 任务失败，从current_tasks中移除
            if "event_groups" in self.current_tasks:
                del self.current_tasks["event_groups"]
        finally:
            db.close()
            
        logger.info("定时相似度和分组任务完成")
        
    def _cleanup_old_cache_job(self):
        """清理过期缓存的定时任务"""
        start_time = datetime.now()
        logger.info("开始执行缓存清理任务")
        self._add_execution_record("cache_cleanup", "running", "开始执行缓存清理任务")
        
        db = SessionLocal()
        try:
            # 清理3天前的缓存记录
            from app.models.event_group import EventGroup
            from datetime import timedelta
            
            self._update_task_progress("cache_cleanup", "正在清理过期缓存记录...")
            
            cutoff_time = datetime.now() - timedelta(days=3)
            
            deleted_count = db.query(EventGroup).filter(
                EventGroup.created_at < cutoff_time
            ).delete(synchronize_session=False)
            
            db.commit()
            
            execution_time = (datetime.now() - start_time).total_seconds()
            message = f"缓存清理完成，用时: {execution_time:.2f}秒，清理了 {deleted_count} 条过期记录"
            
            logger.info(message)
            self._add_execution_record("cache_cleanup", "success", message, {
                'execution_time': execution_time,
                'deleted_count': deleted_count,
                'cutoff_time': cutoff_time.isoformat()
            })
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"缓存清理任务失败: {str(e)}", exc_info=True)
            self._add_execution_record("cache_cleanup", "error", f"缓存清理失败: {str(e)}", {
                'execution_time': execution_time,
                'error_details': str(e)
            })
            db.rollback()
        finally:
            db.close()
            
    def set_event_generation_interval(self, hours: int):
        """设置事件生成间隔"""
        if hours < 1 or hours > 24:
            raise ValueError("事件生成间隔必须在1-24小时之间")
            
        old_interval = self.event_generation_interval
        self.event_generation_interval = hours
        
        # 保存到数据库
        self._save_config_to_database(
            'event_generation_interval', 
            hours, 
            'int', 
            '事件分组生成间隔（小时），范围: 1-24小时'
        )
        
        # 重新设置定时任务
        if self.is_running:
            self._setup_scheduled_jobs()
            
        logger.info(f"事件生成间隔已更新为 {hours} 小时")
        self._add_execution_record("config", "success", f"事件生成间隔从 {old_interval} 小时更新为 {hours} 小时")
        
    def set_crawl_sources_interval(self, hours: float):
        """设置新闻源抓取间隔"""
        if hours < 0.25 or hours > 24:  # 最小15分钟，最大24小时
            raise ValueError("新闻源抓取间隔必须在0.25-24小时之间")
            
        old_interval = self.crawl_sources_interval
        self.crawl_sources_interval = hours
        
        # 保存到数据库
        self._save_config_to_database(
            'crawl_sources_interval', 
            hours, 
            'float', 
            '新闻源抓取间隔（小时），范围: 0.25-24小时'
        )
        
        # 重新设置定时任务
        if self.is_running:
            self._setup_scheduled_jobs()
            
        logger.info(f"新闻源抓取间隔已更新为 {hours} 小时")
        self._add_execution_record("config", "success", f"新闻源抓取间隔从 {old_interval} 小时更新为 {hours} 小时")
        
    def get_status(self) -> dict:
        """获取调度器状态"""
        return {
            'is_running': self.is_running,
            'event_generation_interval': self.event_generation_interval,
            'crawl_sources_interval': self.crawl_sources_interval,
            'scheduled_jobs_count': len(schedule.jobs),
            'next_run_times': [job.next_run.isoformat() if job.next_run else None for job in schedule.jobs if job.next_run],
            'current_tasks': self._get_current_tasks_status()
        }
    
    def _get_current_tasks_status(self) -> Dict:
        """获取当前正在执行的任务状态"""
        current_tasks = {}
        for task_type, task_info in self.current_tasks.items():
            task_status = {
                'status': task_info['status'],
                'message': task_info['message'],
                'start_time': task_info['start_time'].isoformat(),
                'running_time': (datetime.now() - task_info['start_time']).total_seconds(),
                'last_update': task_info.get('last_update', task_info['start_time']).isoformat()
            }
            
            # 添加进度信息（如果有）
            if 'details' in task_info and task_info['details']:
                details = task_info['details']
                if 'current' in details and 'total' in details:
                    task_status['progress'] = {
                        'current': details['current'],
                        'total': details['total'],
                        'percentage': details.get('percentage', 0)
                    }
                    
                # 添加其他详细信息
                task_status['stage_details'] = details
            
            current_tasks[task_type] = task_status
        return current_tasks
        
    def get_execution_history(self, limit: int = 20, task_type: str = None) -> List[Dict]:
        """获取执行历史"""
        history = self.execution_history
        
        if task_type:
            history = [record for record in history if record['task_type'] == task_type]
            
        return history[:limit]
        
    def get_error_history(self, limit: int = 10) -> List[Dict]:
        """获取错误历史"""
        return self.error_history[:limit]
        
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        
        # 最近24小时的执行记录
        recent_records = [
            record for record in self.execution_history 
            if datetime.fromisoformat(record['timestamp']) > last_24h
        ]
        
        # 按任务类型统计
        task_stats = {}
        for record in recent_records:
            task_type = record['task_type']
            if task_type not in task_stats:
                task_stats[task_type] = {'total': 0, 'success': 0, 'error': 0, 'warning': 0, 'running': 0}
            
            task_stats[task_type]['total'] += 1
            status = record['status']
            if status in task_stats[task_type]:
                task_stats[task_type][status] += 1
            else:
                # 处理未预期的状态
                if 'other' not in task_stats[task_type]:
                    task_stats[task_type]['other'] = 0
                task_stats[task_type]['other'] += 1
        
        return {
            'total_executions_24h': len(recent_records),
            'total_errors_24h': len([r for r in recent_records if r['status'] == 'error']),
            'task_statistics': task_stats,
            'last_execution': self.execution_history[0] if self.execution_history else None,
            'current_tasks_count': len(self.current_tasks)
        }
        
    def run_event_generation_now(self, use_multiprocess: bool = True):
        """立即执行事件生成任务"""
        # 检查是否已有相同任务在运行
        if "event_groups" in self.current_tasks:
            logger.warning("事件分组任务已在运行中，跳过本次触发")
            self._add_execution_record("event_groups", "warning", "任务已在运行中，跳过重复执行")
            return {"status": "skipped", "message": "事件分组任务已在运行中，跳过重复执行"}
        
        method = "多进程" if use_multiprocess else "单进程"
        logger.info(f"手动触发事件生成任务（{method}计算）")
        self._add_execution_record("event_groups", "running", f"手动触发事件生成任务（{method}计算）")
        threading.Thread(target=lambda: self._generate_event_groups_job(is_manual_trigger=True, use_multiprocess=use_multiprocess), daemon=True).start()
        return {"status": "started", "message": f"已手动触发事件分组生成任务（{method}计算）"}
        
    def run_crawl_sources_now(self):
        """立即执行新闻源抓取任务"""
        # 检查是否已有相同任务在运行
        if "crawl_sources" in self.current_tasks:
            logger.warning("新闻源抓取任务已在运行中，跳过本次触发")
            self._add_execution_record("crawl_sources", "warning", "任务已在运行中，跳过重复执行")
            return {"status": "skipped", "message": "新闻源抓取任务已在运行中，跳过重复执行"}
            
        logger.info("手动触发新闻源抓取任务")
        self._add_execution_record("crawl_sources", "running", "手动触发新闻源抓取任务")
        threading.Thread(target=self._execute_crawl_sources, daemon=True).start()
        return {"status": "started", "message": "已手动触发新闻源抓取任务"}
    
    def get_task_details(self, timestamp: str) -> Optional[Dict]:
        """获取特定任务的详细信息"""
        for record in self.execution_history:
            if record['timestamp'] == timestamp:
                return record
        return None
        
    def clear_stuck_task(self, task_type: str) -> dict:
        """清理卡住的任务状态"""
        if task_type in self.current_tasks:
            task_info = self.current_tasks[task_type]
            logger.warning(f"手动清理卡住的任务: {task_type}")
            self._add_execution_record(task_type, "warning", f"手动清理卡住的任务，原状态: {task_info['status']}")
            del self.current_tasks[task_type]
            return {"status": "cleared", "message": f"已清理任务 {task_type}"}
        else:
            return {"status": "not_found", "message": f"任务 {task_type} 不存在"}


# 全局调度器实例
scheduler_service = SchedulerService() 