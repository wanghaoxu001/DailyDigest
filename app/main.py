import os
import urllib.parse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
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


# URL解码中间件，处理代理导致的URL编码问题
class URLDecodeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 获取原始路径
        original_path = str(request.url.path)
        original_query = str(request.url.query)
        
        # 记录所有请求路径用于调试
        logger.info(f"中间件收到请求路径: {original_path}")
        
        # 检查是否是被代理编码后部分解码的路径
        # 格式: //185.194.141.108:18899/api/digest/16/pdf
        if original_path.startswith("//") and "185.194.141.108:18899" in original_path:
            try:
                logger.info(f"检测到代理编码路径: {original_path}")
                
                # 查找API路径的开始位置
                api_start = original_path.find("/api/")
                if api_start != -1:
                    # 提取真正的API路径
                    real_path = original_path[api_start:]
                    logger.info(f"提取的API路径: {real_path}")
                    
                    # 检查是否是PDF下载请求
                    if "/pdf" in real_path and request.method in ["GET", "HEAD"]:
                        import re
                        pdf_match = re.search(r'/api/digest/(\d+)/pdf$', real_path)
                        if pdf_match:
                            digest_id = int(pdf_match.group(1))
                            logger.info(f"直接处理PDF下载请求，digest_id: {digest_id}")
                            
                                                        # 导入必要的依赖并直接调用处理函数
                            from app.db.session import get_db
                            from app.api.endpoints.digest import download_digest_pdf
                            
                            # 创建数据库会话
                            db = next(get_db())
                            try:
                                return download_digest_pdf(digest_id, request, db)
                            finally:
                                db.close()
                    
                    # 检查是否是快报详情请求
                    elif real_path.startswith("/api/digest/") and request.method == "GET":
                        import re
                        digest_match = re.search(r'/api/digest/(\d+)$', real_path)
                        if digest_match:
                            digest_id = int(digest_match.group(1))
                            logger.info(f"直接处理快报详情请求，digest_id: {digest_id}")
                            
                            # 导入必要的依赖并直接调用处理函数
                            from app.db.session import get_db
                            from app.api.endpoints.digest import get_digest
                            from fastapi.responses import JSONResponse
                            
                            # 创建数据库会话
                            db = next(get_db())
                            try:
                                # 调用处理函数并转换为JSONResponse
                                result = get_digest(digest_id, db)
                                return JSONResponse(content=result)
                            except Exception as e:
                                logger.error(f"处理快报详情请求失败: {e}")
                                # 继续正常流程
                            finally:
                                db.close()
                else:
                    logger.warning(f"无法在路径中找到API路径: {original_path}")
                    
            except Exception as e:
                logger.error(f"URL处理失败: {e}")
        
        response = await call_next(request)
        return response

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
# 首先添加URL解码中间件（需要最先处理）
app.add_middleware(URLDecodeMiddleware)

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


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点，用于容器和负载均衡器检查服务状态"""
    from datetime import datetime
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Daily Digest System"
    }


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


# 专门处理代理编码URL的路由
@app.get("/http%3A//{rest_of_path:path}")
@app.head("/http%3A//{rest_of_path:path}")
@app.get("http%3A//{rest_of_path:path}")
@app.head("http%3A//{rest_of_path:path}")
async def handle_proxy_encoded_url(rest_of_path: str, request: Request):
    """处理被代理服务器编码的URL"""
    import urllib.parse
    import re
    
    try:
        # 重建完整的编码URL
        full_encoded_url = f"http%3A//{rest_of_path}"
        logger.info(f"检测到代理编码的URL: {full_encoded_url}")
        
        # 解码URL
        decoded_url = urllib.parse.unquote(full_encoded_url)
        logger.info(f"解码后的URL: {decoded_url}")
        
        # 提取API路径
        # 预期格式: http://185.194.141.108:18899/api/digest/16 或 http://185.194.141.108:18899/api/digest/16/pdf
        api_match = re.search(r'http://[^/]+(/api/.+)$', decoded_url)
        if api_match:
            api_path = api_match.group(1)
            logger.info(f"提取的API路径: {api_path}")
            
            # 重定向到正确的API路径
            from fastapi.responses import RedirectResponse
            redirect_url = api_path
            
            # 保持HTTP方法
            if request.method == "HEAD":
                # 对于HEAD请求，我们需要直接调用相应的处理函数
                # 检查是否是PDF下载请求
                pdf_match = re.search(r'/api/digest/(\d+)/pdf$', api_path)
                if pdf_match:
                    digest_id = int(pdf_match.group(1))
                    # 导入必要的依赖
                    from app.db.session import get_db
                    from app.api.endpoints.digest import download_digest_pdf
                    
                    # 创建数据库会话
                    db = next(get_db())
                    try:
                        return download_digest_pdf(digest_id, request, db)
                    finally:
                        db.close()
            
            logger.info(f"重定向到: {redirect_url}")
            return RedirectResponse(url=redirect_url, status_code=307)  # 307保持HTTP方法
        else:
            logger.warning(f"无法从解码URL中提取API路径: {decoded_url}")
            
    except Exception as e:
        logger.error(f"处理代理编码URL失败: {e}")
    
    # 如果处理失败，返回404
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="资源不存在")





if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=18899, reload=True)
