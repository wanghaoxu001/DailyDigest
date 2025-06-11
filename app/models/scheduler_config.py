from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

from app.db.base import Base


class SchedulerConfig(Base):
    """调度器配置模型"""
    __tablename__ = "scheduler_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(100), unique=True, index=True, nullable=False)
    config_value = Column(String(500), nullable=False)
    config_type = Column(String(50), nullable=False, default="string")  # string, int, float, bool
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<SchedulerConfig(key='{self.config_key}', value='{self.config_value}', type='{self.config_type}')>"

    @classmethod
    def get_value(cls, db, key: str, default_value=None, value_type: str = "string"):
        """获取配置值"""
        config = db.query(cls).filter(
            cls.config_key == key,
            cls.is_active == True
        ).first()
        
        if not config:
            return default_value
            
        try:
            if value_type == "float":
                return float(config.config_value)
            elif value_type == "int":
                return int(config.config_value)
            elif value_type == "bool":
                return config.config_value.lower() in ('true', '1', 'yes', 'on')
            else:
                return config.config_value
        except (ValueError, AttributeError):
            return default_value

    @classmethod
    def set_value(cls, db, key: str, value, value_type: str = "string", description: str = None):
        """设置配置值"""
        config = db.query(cls).filter(cls.config_key == key).first()
        
        str_value = str(value)
        
        if config:
            config.config_value = str_value
            config.config_type = value_type
            config.updated_at = datetime.now()
            if description:
                config.description = description
        else:
            config = cls(
                config_key=key,
                config_value=str_value,
                config_type=value_type,
                description=description or f"调度器配置: {key}"
            )
            db.add(config)
        
        db.commit()
        return config 