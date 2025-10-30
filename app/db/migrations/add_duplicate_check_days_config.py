
import sys
import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from app.models.scheduler_config import SchedulerConfig
from app.db.session import SessionLocal

def run_migration():
    db = SessionLocal()
    try:
        # Check if the config already exists
        config_key = "news_duplicate_check_days"
        existing_config = db.query(SchedulerConfig).filter(SchedulerConfig.config_key == config_key).first()

        if not existing_config:
            # Add the new config for duplicate news check days
            new_config = SchedulerConfig(
                config_key=config_key,
                config_value="3",
                config_type="int",
                description="重复新闻检查天数。用于在生成快报时，检查所选新闻是否在过去N天内已经出现过。",
                is_active=True
            )
            db.add(new_config)
            db.commit()
            print(f"Successfully added '{config_key}' to scheduler_configs.")
        else:
            print(f"Config key '{config_key}' already exists. Skipping.")

    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
