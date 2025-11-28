from fastapi import APIRouter

router = APIRouter()

@router.get("/similarity/status")
async def get_similarity_status():
    """获取相似度服务状态（已移除事件分组功能）"""
    return {
        "semantic_model_loaded": False,
        "cache_size": 0,
        "primary_model": "N/A - Feature removed",
        "fallback_model": "N/A - Feature removed",
        "current_model": "Not available",
        "model_type": "removed",
        "cache_limit": 0,
        "status": "disabled",
        "message": "事件分组功能已移除"
    }

@router.post("/similarity/clear-cache")
async def clear_similarity_cache():
    """清空相似度缓存（功能已移除）"""
    return {"message": "Feature removed - no cache to clear"}

@router.post("/similarity/test")
async def test_similarity(text1: str, text2: str):
    """测试文本相似度（功能已移除）"""
    return {
        "text1": text1,
        "text2": text2,
        "char_similarity": 0.0,
        "semantic_similarity": 0.0,
        "message": "Similarity service has been removed"
    }

@router.get("/status")
async def get_system_status():
    """获取系统整体状态"""
    return {"status": "healthy", "message": "系统运行正常（事件分组功能已移除）"}
