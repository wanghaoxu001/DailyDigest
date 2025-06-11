import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn

# 加载环境变量
load_dotenv()

# 设置日志系统
from app.config import setup_logging, get_logger
setup_logging(
    enable_json=os.getenv('ENABLE_JSON_LOGS', 'False').lower() == 'true',
    enable_buffer=os.getenv('ENABLE_LOG_BUFFER', 'True').lower() == 'true',
    max_bytes=int(os.getenv('LOG_MAX_BYTES', '10485760')),
    backup_count=int(os.getenv('LOG_BACKUP_COUNT', '5'))
)
logger = get_logger(__name__)

# 初始化NLTK资源
import app.services

from app.api.router import api_router
from app.db.session import engine, SessionLocal
from app.db.base import Base
from app.db.init_db import init_db
from app.db.update_schema import update_sources_table, run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    Base.metadata.create_all(bind=engine)
    init_db()
    update_sources_table()
    run_migrations()
    logger.info("应用启动完成")
    
    yield
    
    # 关闭时执行
    logger.info("应用正在关闭")
    
    # 停止调度器服务
    try:
        from app.services.scheduler import scheduler_service
        scheduler_service.stop()
        logger.info("调度器服务已停止")
    except Exception as e:
        logger.error(f"停止调度器服务时出错: {e}")


# 创建应用
app = FastAPI(title="每日安全快报系统", lifespan=lifespan)

# 配置中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 设置模板
templates = Jinja2Templates(directory="app/templates")

# 初始化路由
app.include_router(api_router)


# 前端首页路由
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# 新闻页面路由
@app.get("/news")
async def news_page(request: Request):
    return templates.TemplateResponse("news.html", {"request": request})


# 快报页面路由
@app.get("/digest")
async def digest_page(request: Request):
    return templates.TemplateResponse("digest.html", {"request": request})


# 快报详情页面路由
@app.get("/digest/{digest_id}")
async def digest_detail_page(request: Request, digest_id: int):
    return templates.TemplateResponse("digest.html", {"request": request})


# 管理页面路由
@app.get("/admin")
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})





if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=18899, reload=True)
