from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from datetime import datetime

from app.db.base import Base


class CronConfig(Base):
    """Cron调度配置模型"""
    __tablename__ = "cron_configs"

    id = Column(Integer, primary_key=True, index=True)
    task_name = Column(String(100), unique=True, nullable=False, index=True)
    cron_expression = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    def __repr__(self):
        return f"<CronConfig(task_name='{self.task_name}', cron='{self.cron_expression}', enabled={self.enabled})>"

    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'task_name': self.task_name,
            'cron_expression': self.cron_expression,
            'enabled': self.enabled,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def get_enabled_configs(cls, db):
        """获取所有启用的配置"""
        return db.query(cls).filter(cls.enabled == True).all()

    @classmethod
    def get_config_by_name(cls, db, task_name: str):
        """根据任务名获取配置"""
        return db.query(cls).filter(cls.task_name == task_name).first()

    @classmethod
    def update_config(cls, db, task_name: str, cron_expression: str = None, 
                     enabled: bool = None, description: str = None):
        """更新配置"""
        config = cls.get_config_by_name(db, task_name)
        if not config:
            return None
        
        if cron_expression is not None:
            config.cron_expression = cron_expression
        if enabled is not None:
            config.enabled = enabled
        if description is not None:
            config.description = description
        
        config.updated_at = datetime.now()
        db.commit()
        db.refresh(config)
        return config

