from fastapi import APIRouter

from app.api.endpoints import news, sources, digest, similarity_status, logs, similarity_management, task_executions

api_router = APIRouter(prefix="/api")
 
# 重新排序路由注册，确保更具体的路由先注册
api_router.include_router(sources.router, prefix="/sources", tags=["新闻源"])
api_router.include_router(news.router, prefix="/news", tags=["新闻"])
api_router.include_router(digest.router, prefix="/digest", tags=["快报"])
api_router.include_router(logs.router, prefix="/logs", tags=["日志管理"])
api_router.include_router(task_executions.router, prefix="/scheduler", tags=["任务执行记录"])
api_router.include_router(similarity_status.router, prefix="/system", tags=["系统状态"])
api_router.include_router(similarity_management.router, prefix="/similarity", tags=["相似度管理"]) 