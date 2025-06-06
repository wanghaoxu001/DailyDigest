from fastapi import APIRouter
from app.services.news_similarity import similarity_service

router = APIRouter()

@router.get("/similarity/status")
async def get_similarity_status():
    """获取相似度服务状态"""
    stats = similarity_service.get_cache_stats()
    
    # 获取当前加载的模型信息
    model = similarity_service.get_semantic_model()
    current_model_name = "Not loaded"
    model_type = "unknown"
    
    if model:
        if hasattr(model, 'model_type') and model.model_type == 'bge':
            current_model_name = similarity_service._semantic_model_name
            model_type = "BGE (FlagEmbedding)"
        else:
            current_model_name = similarity_service._fallback_model_name
            model_type = "SentenceTransformers"
    
    return {
        "semantic_model_loaded": stats.get("model_loaded", False),
        "cache_size": stats.get("cache_size", 0),
        "primary_model": similarity_service._semantic_model_name,
        "fallback_model": similarity_service._fallback_model_name,
        "current_model": current_model_name,
        "model_type": model_type,
        "cache_limit": 1000,
        "status": "healthy" if stats.get("model_loaded", False) else "degraded"
    }

@router.post("/similarity/clear-cache")
async def clear_similarity_cache():
    """清空相似度缓存"""
    similarity_service.clear_cache()
    return {"message": "Similarity cache cleared successfully"}

@router.post("/similarity/test")
async def test_similarity(text1: str, text2: str):
    """测试文本相似度"""
    try:
        char_similarity = similarity_service.calculate_text_similarity(text1, text2)
        semantic_similarity = similarity_service.calculate_semantic_similarity(text1, text2)
        
        return {
            "text1": text1,
            "text2": text2,
            "character_similarity": round(char_similarity, 3),
            "semantic_similarity": round(semantic_similarity, 3),
            "mixed_strategy_result": round(char_similarity, 3)
        }
    except Exception as e:
        return {
            "error": str(e),
            "text1": text1,
            "text2": text2
        } 