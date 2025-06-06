"""
运行所有数据库迁移脚本
"""

import logging
import os
import importlib.util
import sys

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入迁移模块
from app.db.migrations.add_article_summary import run_migration as add_article_summary
from app.db.migrations.add_newspaper_keywords import run_migration as add_newspaper_keywords
from app.db.migrations.add_summary_source import run_migration as add_summary_source
from app.db.migrations.add_tokens_counter import run_migration as add_tokens_counter
from app.db.migrations.add_detailed_tokens import run_migration as add_detailed_tokens
from app.db.migrations.fix_token_decimals import run_migration as fix_token_decimals

def run_all_migrations(db_path="daily_digest.db"):
    """运行所有迁移脚本"""
    logger.info(f"开始运行所有迁移脚本，数据库路径: {db_path}")
    
    # 迁移脚本目录
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    
    if not os.path.exists(migrations_dir):
        logger.warning(f"迁移目录不存在: {migrations_dir}")
        os.makedirs(migrations_dir)
        logger.info(f"已创建迁移目录: {migrations_dir}")
    
    # 获取所有迁移脚本
    migration_files = sorted([f for f in os.listdir(migrations_dir) 
                             if f.endswith('.py') and not f.startswith('__')])
    
    if not migration_files:
        logger.warning("没有找到迁移脚本")
        return
    
    logger.info(f"找到 {len(migration_files)} 个迁移脚本")
    
    # 执行每个迁移脚本
    for migration_file in migration_files:
        migration_path = os.path.join(migrations_dir, migration_file)
        logger.info(f"执行迁移: {migration_file}")
        
        try:
            # 动态加载迁移模块
            spec = importlib.util.spec_from_file_location(
                f"migration_{migration_file}", migration_path)
            migration_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration_module)
            
            # 运行迁移
            if hasattr(migration_module, 'run_migration'):
                result = migration_module.run_migration(db_path)
                if result:
                    logger.info(f"迁移 {migration_file} 成功完成")
                else:
                    logger.warning(f"迁移 {migration_file} 不需要执行或已执行过")
            else:
                logger.error(f"迁移 {migration_file} 没有run_migration函数")
        except Exception as e:
            logger.error(f"执行迁移 {migration_file} 失败: {str(e)}")
    
    logger.info("所有迁移脚本执行完毕")

def run_migrations(db_path="daily_digest.db"):
    """
    执行所有必要的迁移
    
    参数:
    - db_path: 数据库文件路径
    
    返回:
    - 布尔值，表示是否有任何迁移被执行
    """
    
    # 执行迁移并收集结果
    results = []
    results.append(add_article_summary(db_path))
    results.append(add_newspaper_keywords(db_path))
    results.append(add_summary_source(db_path))
    results.append(add_tokens_counter(db_path))
    results.append(add_detailed_tokens(db_path))
    results.append(fix_token_decimals(db_path))
    
    # 如果有任何一个迁移被执行，则返回True
    return any(results)

if __name__ == "__main__":
    # 可以通过命令行参数指定数据库路径
    db_path = "daily_digest.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        
    run_all_migrations(db_path)
    print("迁移过程完成，请检查日志获取详细信息。")

    # 当脚本直接运行时执行所有迁移
    run_migrations() 