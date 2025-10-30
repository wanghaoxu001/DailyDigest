#!/usr/bin/env python3
"""
安装crontab脚本
从数据库读取cron配置并安装到系统crontab
用于容器启动时和配置更新后
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.cron_manager import cron_manager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    try:
        logger.info("=" * 60)
        logger.info("开始安装crontab配置")
        logger.info("=" * 60)
        
        # 重新加载crontab
        result = cron_manager.reload_crontab()
        
        if result['status'] == 'success':
            logger.info(f"✓ {result['message']}")
            
            # 验证安装
            verification = cron_manager.verify_crontab()
            if verification['verified']:
                logger.info(f"✓ 验证通过: {verification['message']}")
            else:
                logger.warning(f"⚠ 验证警告: {verification['message']}")
            
            # 显示当前crontab
            current_crontab = cron_manager.get_current_crontab()
            if current_crontab:
                logger.info("\n当前系统crontab内容:")
                logger.info("-" * 60)
                for line in current_crontab.split('\n'):
                    logger.info(line)
                logger.info("-" * 60)
            
            sys.exit(0)
        else:
            logger.error(f"✗ {result['message']}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"安装crontab失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()

