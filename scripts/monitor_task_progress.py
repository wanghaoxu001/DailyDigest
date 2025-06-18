#!/usr/bin/env python3
"""
实时任务进度监控脚本
用于监控定时任务的执行进度和状态
"""

import requests
import time
import sys
import json
from datetime import datetime
import signal

# 服务器配置
SERVER_URL = "http://localhost:18899"
REFRESH_INTERVAL = 2  # 秒

class TaskProgressMonitor:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, sig, frame):
        """处理Ctrl+C信号"""
        print('\n\n👋 监控已停止')
        self.running = False
        sys.exit(0)
    
    def get_scheduler_status(self):
        """获取调度器状态"""
        try:
            response = requests.get(f"{SERVER_URL}/api/sources/scheduler/status", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except Exception as e:
            print(f"❌ 获取状态失败: {e}")
            return None
    
    def format_progress_bar(self, current, total, width=40):
        """格式化进度条"""
        if total <= 0:
            return "[" + "?" * width + "]"
        
        percentage = min(current / total, 1.0)
        filled = int(width * percentage)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percentage*100:.1f}%"
    
    def format_duration(self, seconds):
        """格式化时间"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            return f"{seconds//60:.0f}分{seconds%60:.0f}秒"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours:.0f}时{minutes:.0f}分"
    
    def get_task_type_name(self, task_type):
        """获取任务类型中文名称"""
        names = {
            'crawl_sources': '新闻源抓取',
            'event_groups': '相似度计算与分组',
            'cache_cleanup': '缓存清理',
            'system': '系统任务'
        }
        return names.get(task_type, task_type)
    
    def display_task_progress(self, task_type, task_data):
        """显示单个任务的进度"""
        print(f"📋 任务类型: {self.get_task_type_name(task_type)}")
        print(f"📊 状态: {task_data['status']}")
        print(f"💬 当前消息: {task_data['message']}")
        print(f"⏱️ 运行时间: {self.format_duration(task_data['running_time'])}")
        
        # 显示进度条（如果有进度信息）
        if 'progress' in task_data and task_data['progress']:
            progress = task_data['progress']
            current = progress.get('current', 0)
            total = progress.get('total', 0)
            percentage = progress.get('percentage', 0)
            
            if total > 0:
                progress_bar = self.format_progress_bar(current, total)
                print(f"📈 进度: {progress_bar} ({current}/{total})")
            else:
                print(f"📈 进度: {percentage:.1f}%")
        
        # 显示详细信息（如果有）
        if 'stage_details' in task_data and task_data['stage_details']:
            details = task_data['stage_details']
            
            # 阶段信息
            if 'stage' in details:
                stage_names = {
                    'similarity_calculation': '🔗 相似度计算',
                    'group_computation': '📚 事件分组',
                    'cache_generation': '💾 缓存生成',
                    'cleanup': '🧹 清理工作',
                    'crawling': '🕸️ 数据抓取'
                }
                stage_name = stage_names.get(details['stage'], details['stage'])
                print(f"🎯 阶段: {stage_name}")
            
            # 具体统计信息
            if 'successful_crawls' in details:
                print(f"✅ 成功: {details['successful_crawls']}")
            if 'skipped_sources' in details:
                print(f"⏭️ 跳过: {details['skipped_sources']}")
            if 'calculated_pairs' in details:
                print(f"🔗 已计算配对: {details['calculated_pairs']}")
            if 'skipped_pairs' in details:
                print(f"⏭️ 跳过配对: {details['skipped_pairs']}")
            if 'current_source' in details:
                print(f"📡 当前源: {details['current_source']}")
            if 'workers' in details:
                print(f"🔧 工作进程: {details['workers']}")
            if 'completed_batches' in details and 'total_batches' in details:
                print(f"📦 批次: {details['completed_batches']}/{details['total_batches']}")
            
            # 显示当前处理的新闻标题（截取显示）
            if 'current_news1' in details:
                title1 = details['current_news1'][:50] + "..." if len(details['current_news1']) > 50 else details['current_news1']
                print(f"📰 对比文章1: {title1}")
            if 'current_news2' in details:
                title2 = details['current_news2'][:50] + "..." if len(details['current_news2']) > 50 else details['current_news2']
                print(f"📰 对比文章2: {title2}")
    
    def clear_screen(self):
        """清屏"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def monitor_tasks(self):
        """监控任务进度"""
        print("🚀 启动任务进度监控...")
        print(f"🔄 刷新间隔: {REFRESH_INTERVAL}秒")
        print("📡 监控地址:", SERVER_URL)
        print("💡 按 Ctrl+C 停止监控\n")
        
        while self.running:
            try:
                status = self.get_scheduler_status()
                
                if not status:
                    print("❌ 无法获取调度器状态，请检查服务是否运行")
                    time.sleep(REFRESH_INTERVAL)
                    continue
                
                # 清屏并显示最新状态
                self.clear_screen()
                
                # 显示时间戳
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"⏰ 最后更新: {current_time}")
                print("=" * 60)
                
                # 显示调度器基本状态
                if status['is_running']:
                    print("🟢 调度器状态: 运行中")
                else:
                    print("🔴 调度器状态: 已停止")
                
                print(f"⚙️ 计划任务数: {status['scheduled_jobs_count']}")
                
                # 显示当前正在执行的任务
                current_tasks = status.get('current_tasks', {})
                
                if current_tasks:
                    print(f"\n🔄 正在执行的任务 ({len(current_tasks)}个):")
                    print("-" * 60)
                    
                    for task_type, task_data in current_tasks.items():
                        self.display_task_progress(task_type, task_data)
                        print("-" * 40)
                else:
                    print("\n💤 当前没有正在执行的任务")
                
                # 显示提示信息
                print(f"\n💡 刷新间隔: {REFRESH_INTERVAL}秒 | 按 Ctrl+C 停止监控")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ 监控出错: {e}")
            
            time.sleep(REFRESH_INTERVAL)
    
    def show_current_status(self):
        """显示当前状态（一次性）"""
        status = self.get_scheduler_status()
        
        if not status:
            print("❌ 无法获取调度器状态")
            return
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"⏰ 查询时间: {current_time}")
        print("=" * 60)
        
        # 基本状态
        if status['is_running']:
            print("🟢 调度器状态: 运行中")
        else:
            print("🔴 调度器状态: 已停止")
        
        print(f"⚙️ 计划任务数: {status['scheduled_jobs_count']}")
        
        # 当前任务
        current_tasks = status.get('current_tasks', {})
        
        if current_tasks:
            print(f"\n🔄 正在执行的任务 ({len(current_tasks)}个):")
            print("-" * 60)
            
            for task_type, task_data in current_tasks.items():
                self.display_task_progress(task_type, task_data)
                print("-" * 40)
        else:
            print("\n💤 当前没有正在执行的任务")

def main():
    """主函数"""
    monitor = TaskProgressMonitor()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "monitor":
            monitor.monitor_tasks()
        elif command == "status":
            monitor.show_current_status()
        elif command == "help":
            print("📋 任务进度监控脚本使用说明:")
            print("python monitor_task_progress.py          - 显示当前状态")
            print("python monitor_task_progress.py monitor  - 持续监控模式")
            print("python monitor_task_progress.py status   - 显示当前状态")
            print("python monitor_task_progress.py help     - 显示帮助信息")
        else:
            print(f"❌ 未知命令: {command}")
            print("💡 使用 'python monitor_task_progress.py help' 查看帮助")
    else:
        # 默认显示当前状态
        monitor.show_current_status()

if __name__ == "__main__":
    main() 