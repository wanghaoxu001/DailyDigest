import sys
import os
import uvicorn
from dotenv import load_dotenv

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 加载环境变量
load_dotenv()

# 解决 Hugging Face tokenizers 并行冲突问题
# 在导入任何可能使用tokenizers的库之前设置此环境变量
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# 导入数据库更新函数
from app.db.update_schema import update_sources_table, run_migrations

if __name__ == "__main__":
    # 获取配置
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "18899"))
    reload = os.getenv("DEBUG", "False").lower() == "true"

    # 更新数据库结构
    print("检查并更新数据库结构...")
    update_sources_table()

    # 执行数据库迁移
    print("执行数据库迁移...")
    run_migrations()

    print(
        f"启动每日安全快报系统，访问地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}"
    )

    # 初始化cron配置（从数据库读取并安装到系统cron）
    try:
        from app.services.cron_manager import cron_manager
        result = cron_manager.reload_crontab()
        if result['status'] == 'success':
            print("✓ Cron配置已加载并安装到系统")
        else:
            print(f"⚠ Cron配置加载失败: {result['message']}")
    except Exception as e:
        print(f"⚠ 加载cron配置时出错: {e}")

    # 启动应用
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
