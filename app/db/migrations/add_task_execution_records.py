"""
添加任务执行记录表

用于持久化存储定时任务的执行历史记录
"""

import logging
from sqlalchemy import text
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

def upgrade():
    """升级数据库 - 添加任务执行记录表"""
    db = SessionLocal()
    try:
        logger.info("开始添加任务执行记录表...")
        
        # 创建任务执行记录表
        create_table_sql = text("""
        CREATE TABLE IF NOT EXISTS task_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type VARCHAR(100) NOT NULL,
            task_id VARCHAR(200),
            status VARCHAR(50) NOT NULL,
            message TEXT,
            details JSON,
            
            -- 时间记录
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            duration_seconds INTEGER,
            
            -- 进度记录
            progress_current INTEGER,
            progress_total INTEGER,
            progress_percentage INTEGER,
            
            -- 结果统计
            items_processed INTEGER,
            items_success INTEGER,
            items_failed INTEGER,
            
            -- 系统信息
            hostname VARCHAR(100),
            process_id INTEGER,
            
            -- 错误信息
            error_type VARCHAR(200),
            error_message TEXT,
            stack_trace TEXT,
            
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        db.execute(create_table_sql)
        
        # 创建索引
        indexes_sql = [
            "CREATE INDEX IF NOT EXISTS idx_task_executions_task_type ON task_executions(task_type)",
            "CREATE INDEX IF NOT EXISTS idx_task_executions_task_id ON task_executions(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_executions_status ON task_executions(status)",
            "CREATE INDEX IF NOT EXISTS idx_task_executions_start_time ON task_executions(start_time)",
            "CREATE INDEX IF NOT EXISTS idx_task_executions_end_time ON task_executions(end_time)",
            "CREATE INDEX IF NOT EXISTS idx_task_executions_created_at ON task_executions(created_at)"
        ]
        
        for index_sql in indexes_sql:
            db.execute(text(index_sql))
        
        # 创建触发器来自动更新 updated_at 字段
        trigger_sql = text("""
        CREATE TRIGGER IF NOT EXISTS update_task_executions_updated_at
        AFTER UPDATE ON task_executions
        FOR EACH ROW
        BEGIN
            UPDATE task_executions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END
        """)
        
        db.execute(trigger_sql)
        
        db.commit()
        logger.info("任务执行记录表创建成功")
        
        # 添加一些初始配置
        from app.models.scheduler_config import SchedulerConfig
        
        # 设置任务执行记录保留天数
        SchedulerConfig.set_value(
            db, 
            'task_execution_retention_days', 
            30, 
            'int', 
            '任务执行记录保留天数'
        )
        
        # 设置是否启用详细日志记录
        SchedulerConfig.set_value(
            db, 
            'enable_detailed_task_logging', 
            True, 
            'bool', 
            '是否启用详细的任务执行日志记录'
        )
        
        logger.info("任务执行记录相关配置初始化完成")
        
    except Exception as e:
        db.rollback()
        logger.error(f"添加任务执行记录表失败: {e}")
        raise
    finally:
        db.close()

def downgrade():
    """降级数据库 - 删除任务执行记录表"""
    db = SessionLocal()
    try:
        logger.info("开始删除任务执行记录表...")
        
        # 删除触发器
        db.execute(text("DROP TRIGGER IF EXISTS update_task_executions_updated_at"))
        
        # 删除表
        db.execute(text("DROP TABLE IF EXISTS task_executions"))
        
        # 删除相关配置
        from app.models.scheduler_config import SchedulerConfig
        db.query(SchedulerConfig).filter(
            SchedulerConfig.config_key.in_([
                'task_execution_retention_days',
                'enable_detailed_task_logging'
            ])
        ).delete()
        
        db.commit()
        logger.info("任务执行记录表删除成功")
        
    except Exception as e:
        db.rollback()
        logger.error(f"删除任务执行记录表失败: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    # 可以直接运行此文件来执行迁移
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        downgrade()
    else:
        upgrade()
    print("任务执行记录表迁移完成") 