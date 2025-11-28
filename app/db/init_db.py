import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# 导入项目模块
from app.db.base import Base
from app.db.session import engine
from app.models.source import Source
from app.models.news import News
from app.models.digest import Digest

def init_db():
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    print("数据库初始化完成")

if __name__ == "__main__":
    init_db() 