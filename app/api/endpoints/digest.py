from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime, date
import os
import markdown
import pytz

from app.db.session import get_db
from app.models.digest import Digest
from app.models.news import News, NewsCategory
from app.services.digest_generator import create_digest_content, generate_pdf
from app.services.duplicate_detector import duplicate_detector_service
from app.api.endpoints.news import news_to_dict
from app.config.paths import get_pdf_absolute_path
from app.config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 北京时区
BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def format_datetime_with_tz(dt):
    """将datetime对象格式化为带时区信息的ISO字符串"""
    if dt is None:
        return None
    
    # 如果datetime是naive（没有时区信息），假设它是UTC时间
    if dt.tzinfo is None:
        import pytz
        dt = pytz.UTC.localize(dt)
    
    # 转换到北京时区
    dt = dt.astimezone(BEIJING_TZ)
    
    return dt.isoformat()

# 请求和响应模型
class DigestBase(BaseModel):
    title: str
    date: datetime

class DigestCreate(DigestBase):
    selected_news_ids: List[int]

class DigestUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class DigestResponse(DigestBase):
    id: int
    content: Optional[str] = None
    pdf_path: Optional[str] = None
    news_counts: Optional[Dict[str, int]] = None
    created_at: str

    # 在Pydantic v2中使用model_config
    model_config = {"from_attributes": True}

class DigestNewsResponse(BaseModel):
    id: int
    title: str
    generated_title: str
    generated_summary: str
    category: str

    # 在Pydantic v2中使用model_config
    model_config = {"from_attributes": True}

class DigestDetailResponse(DigestResponse):
    news_items: List[DigestNewsResponse] = []
    news_ids: List[int] = []  # 关联新闻的ID列表，用于前端判断哪些新闻可以查看详情

class DigestPreviewRequest(BaseModel):
    content: str
    title: str
    date: str

# 辅助函数 - 将ORM模型转换为字典
def digest_to_dict(digest: Digest) -> dict:
    """将数据库Digest模型转换为适合API响应的字典"""
    return {
        "id": digest.id,
        "title": digest.title,
        "date": format_datetime_with_tz(digest.date),
        "content": digest.content,
        "pdf_path": digest.pdf_path,
        "news_counts": digest.news_counts,
        "created_at": format_datetime_with_tz(digest.created_at)
    }

def digest_detail_to_dict(digest: Digest, db: Session = None) -> dict:
    """将数据库Digest模型转换为详细响应字典，包括关联的新闻和重复检测状态"""
    # 基本信息
    digest_dict = digest_to_dict(digest)

    # 获取重复检测状态
    duplicate_status = {}
    if db:
        try:
            duplicate_status = duplicate_detector_service.get_duplicate_detection_status(digest.id, db)
        except Exception as e:
            logger.warning(f"获取重复检测状态失败: {e}")

    # 添加关联的新闻条目
    news_items = []
    news_ids = []
    for news in digest.news_items:
        news_item = {
            "id": news.id,
            "title": news.title,
            "generated_title": news.generated_title or "",
            "generated_summary": news.generated_summary or "",
            "category": news.category.value if news.category else "其他"
        }

        # 添加重复检测状态
        if news.id in duplicate_status:
            news_item["duplicate_detection"] = duplicate_status[news.id]
        else:
            # 如果没有检测记录，设置默认状态
            news_item["duplicate_detection"] = {
                "status": "checking",
                "duplicate_with_news_id": None,
                "similarity_score": None,
                "llm_reasoning": None,
                "checked_at": None
            }

        news_items.append(news_item)
        news_ids.append(news.id)

    digest_dict["news_items"] = news_items
    digest_dict["news_ids"] = news_ids
    return digest_dict

# API端点
@router.get("/", response_model=List[DigestResponse])
def get_digests(
    skip: int = 0,
    limit: int = 20, 
    db: Session = Depends(get_db)
):
    """获取所有快报列表"""
    digests = db.query(Digest).order_by(Digest.date.desc()).offset(skip).limit(limit).all()
    # 手动转换ORM对象到字典
    return [digest_to_dict(digest) for digest in digests]


# 兼容无尾斜杠路径 /api/digest
@router.get("", response_model=List[DigestResponse])
def get_digests_no_slash(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    return get_digests(skip=skip, limit=limit, db=db)

@router.post("/", response_model=DigestResponse, status_code=status.HTTP_201_CREATED)
def create_digest(digest_create: DigestCreate, db: Session = Depends(get_db)):
    """创建新的快报"""
    # 检查所选新闻是否存在
    selected_news = db.query(News).filter(News.id.in_(digest_create.selected_news_ids)).all()
    
    if len(selected_news) != len(digest_create.selected_news_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="部分所选新闻不存在"
        )
    
    # 生成快报内容
    content = create_digest_content(selected_news)
    
    # 统计各分类的新闻数量
    category_counts = {}
    for news in selected_news:
        category = news.category.value if news.category else "其他"
        category_counts[category] = category_counts.get(category, 0) + 1
    
    # 创建快报记录
    digest = Digest(
        title=digest_create.title,
        date=digest_create.date,
        content=content,
        news_counts=category_counts
    )
    
    try:
        # 关联新闻
        digest.news_items = selected_news
        
        # 标记所有相关新闻为已使用
        for news in selected_news:
            news.is_used_in_digest = True
        
        db.add(digest)
        db.commit()
        db.refresh(digest)

        # 启动异步重复检测
        try:
            duplicate_detector_service.detect_duplicates_for_digest(
                digest.id, digest_create.selected_news_ids
            )
            logger.info(f"已启动快报 {digest.id} 的重复检测")
        except Exception as e:
            logger.warning(f"启动重复检测失败: {e}")
            # 不影响快报创建的主要流程

    except Exception as e:
        db.rollback()
        logger.error(f"创建快报失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建快报失败: {str(e)}",
        )

    # 手动转换ORM对象到字典
    return digest_to_dict(digest)


# 兼容无尾斜杠路径 POST /api/digest
@router.post("", response_model=DigestResponse, status_code=status.HTTP_201_CREATED)
def create_digest_no_slash(digest_create: DigestCreate, db: Session = Depends(get_db)):
    return create_digest(digest_create, db)

@router.get("/latest", response_model=Optional[DigestResponse])
def get_latest_digest(db: Session = Depends(get_db)):
    """获取最新的快报"""
    latest_digest = db.query(Digest).order_by(Digest.created_at.desc()).first()
    
    if not latest_digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="没有找到任何快报"
        )
    
    # 手动转换ORM对象到字典
    return digest_to_dict(latest_digest)

@router.get("/count")
def get_digests_count(db: Session = Depends(get_db)):
    """获取快报总数量"""
    count = db.query(Digest).count()
    return {"count": count}

@router.get("/yesterday/last-created")
def get_yesterday_last_digest_time(db: Session = Depends(get_db)):
    """获取昨天最后一次生成快报的时间"""
    from datetime import datetime, timedelta, time
    
    # 获取北京时间的当前时间
    now_beijing = datetime.now(BEIJING_TZ)
    today = now_beijing.date()
    
    # 构建昨天的日期范围（北京时间）
    yesterday_start_beijing = BEIJING_TZ.localize(datetime.combine(today - timedelta(days=1), time.min))
    yesterday_end_beijing = BEIJING_TZ.localize(datetime.combine(today, time.min))
    
    # 转换为UTC时间进行数据库查询（因为数据库存储的是UTC时间）
    yesterday_start_utc = yesterday_start_beijing.astimezone(pytz.UTC).replace(tzinfo=None)
    yesterday_end_utc = yesterday_end_beijing.astimezone(pytz.UTC).replace(tzinfo=None)
    
    # 查询昨天创建的最后一个快报
    last_digest = (
        db.query(Digest)
        .filter(Digest.created_at >= yesterday_start_utc)
        .filter(Digest.created_at < yesterday_end_utc)
        .order_by(Digest.created_at.desc())
        .first()
    )
    
    if not last_digest:
        return {
            "has_digest": False,
            "last_digest_time": None,
            "message": "昨天没有生成任何快报"
        }
    
    return {
        "has_digest": True,
        "last_digest_time": format_datetime_with_tz(last_digest.created_at),
        "message": f"昨天最后一次快报生成于 {format_datetime_with_tz(last_digest.created_at)}"
    }

@router.get("/{digest_id}", response_model=DigestDetailResponse)
def get_digest(digest_id: int, db: Session = Depends(get_db)):
    """获取特定快报详情"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )
    
    # 手动转换ORM对象到详细字典
    return digest_detail_to_dict(digest, db)

@router.put("/{digest_id}", response_model=DigestResponse)
def update_digest(digest_id: int, digest_update: DigestUpdate, db: Session = Depends(get_db)):
    """更新快报内容"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )
    
    update_data = digest_update.dict(exclude_unset=True)
    
    # 如果更新了内容，则清除旧的PDF文件路径，确保重新生成PDF
    if 'content' in update_data or 'title' in update_data:
        # 删除旧的PDF文件
        if digest.pdf_path:
            try:
                from app.config.paths import get_pdf_absolute_path
                old_pdf_path = get_pdf_absolute_path(digest.pdf_path)
                if old_pdf_path.exists():
                    old_pdf_path.unlink()
                    logger.info(f"已删除旧PDF文件: {old_pdf_path}")
            except Exception as e:
                logger.warning(f"删除旧PDF文件失败: {str(e)}")
        
        # 清除PDF路径，强制重新生成
        digest.pdf_path = None
        logger.info(f"快报 {digest_id} 内容已更新，PDF路径已清除")
    
    try:
        for key, value in update_data.items():
            setattr(digest, key, value)
        
        db.commit()
        db.refresh(digest)
    except Exception as e:
        db.rollback()
        logger.error(f"更新快报失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新快报失败: {str(e)}",
        )
    
    # 手动转换ORM对象到字典
    return digest_to_dict(digest)

@router.post("/{digest_id}/generate-pdf", response_model=DigestResponse)
def generate_digest_pdf(
    digest_id: int, 
    use_typora: bool = False,
    db: Session = Depends(get_db)
):
    """生成快报的PDF文件"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )
    
    # 根据参数选择渲染器生成PDF
    if use_typora:
        try:
            from app.services.playwright_pdf_generator import generate_pdf_typora
            pdf_path = generate_pdf_typora(digest)
            logger.info(f"使用Typora渲染器生成PDF: {pdf_path}")
        except Exception as e:
            logger.error(f"Typora渲染器生成PDF失败，回退到原有渲染器: {e}")
            pdf_path = generate_pdf(digest)
    else:
        pdf_path = generate_pdf(digest)
    
    if pdf_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF生成服务不可用，请检查系统是否已安装Playwright所需的依赖"
        )
    
    # 更新快报记录的PDF路径
    try:
        digest.pdf_path = pdf_path
        db.commit()
        db.refresh(digest)
    except Exception as e:
        db.rollback()
        logger.error(f"更新PDF路径失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新PDF路径失败: {str(e)}",
        )
    
    # 手动转换ORM对象到字典
    return digest_to_dict(digest)

@router.head("/{digest_id}/pdf")
@router.get("/{digest_id}/pdf")
def download_digest_pdf(digest_id: int, request: Request, db: Session = Depends(get_db)):
    """下载快报PDF"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )
    
    if not digest.pdf_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF文件不存在，请先生成PDF"
        )
    
    # 使用统一的路径管理获取绝对路径
    pdf_absolute_path = get_pdf_absolute_path(digest.pdf_path)
    
    # 检查文件是否存在
    if not pdf_absolute_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PDF文件不存在或已被删除"
        )
    
    # 生成中文文件名格式：每日网安情报速递【yyyyMMdd】.pdf
    try:
        date_str = digest.date.strftime('%Y%m%d')
        safe_filename = f"每日网安情报速递【{date_str}】.pdf"
        logger.info(f"生成下载文件名: {safe_filename}")
    except Exception as e:
        logger.error(f"生成文件名失败: {str(e)}")
        # 使用备用文件名
        safe_filename = f"digest_{digest.id}.pdf"
    
    # 如果是HEAD请求，只返回headers不返回内容
    if request.method == "HEAD":
        try:
            logger.info(f"处理HEAD请求，文件路径: {pdf_absolute_path}")
            file_size = pdf_absolute_path.stat().st_size
            logger.info(f"文件大小: {file_size} bytes")
            
            # 对中文文件名进行URL编码
            import urllib.parse
            encoded_filename = urllib.parse.quote(safe_filename, safe='')
            
            return Response(
                content="",
                status_code=200,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="digest.pdf"; filename*=UTF-8\'\'{encoded_filename}',
                    "Content-Length": str(file_size),
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache", 
                    "Expires": "0",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY"
                }
            )
        except Exception as e:
            logger.error(f"HEAD请求处理失败: {str(e)}")
            logger.error(f"文件路径: {pdf_absolute_path}")
            logger.error(f"文件存在: {pdf_absolute_path.exists()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取PDF文件信息失败: {str(e)}"
            )
    
    # GET请求返回文件内容
    try:
        logger.info(f"处理GET请求，开始读取文件: {pdf_absolute_path}")
        with open(pdf_absolute_path, "rb") as file:
            content = file.read()
        
        logger.info(f"文件读取成功，大小: {len(content)} bytes")
        
        # 对中文文件名进行URL编码
        import urllib.parse
        encoded_filename = urllib.parse.quote(safe_filename, safe='')
        
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="digest.pdf"; filename*=UTF-8\'\'{encoded_filename}',
                "Content-Length": str(len(content)),
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY"
            }
        )
    except Exception as e:
        logger.error(f"GET请求处理失败: {str(e)}")
        logger.error(f"文件路径: {pdf_absolute_path}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取PDF文件失败: {str(e)}"
        )

@router.get("/{digest_id}/preview")
def preview_digest(digest_id: int, db: Session = Depends(get_db)):
    """实时预览快报"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )
    
    # 将快报内容转换为HTML格式
    md = markdown.Markdown(
        extensions=[
            'markdown.extensions.extra',
            'markdown.extensions.codehilite',
            'markdown.extensions.toc',
            'markdown.extensions.tables',
            'markdown.extensions.nl2br'
        ],
        extension_configs={
            'codehilite': {
                'css_class': 'highlight'
            }
        }
    )
    
    html_content = md.convert(digest.content or '')
    
    return {
        "title": digest.title,
        "date": digest.date.isoformat() if digest.date else None,
        "content": html_content
    }

@router.post("/preview")
def preview_digest_content(preview_request: DigestPreviewRequest):
    """预览Markdown内容（不保存）"""
    # 将Markdown内容转换为HTML
    md = markdown.Markdown(
        extensions=[
            'markdown.extensions.extra',
            'markdown.extensions.codehilite',
            'markdown.extensions.toc',
            'markdown.extensions.tables',
            'markdown.extensions.nl2br'
        ],
        extension_configs={
            'codehilite': {
                'css_class': 'highlight'
            }
        }
    )

    html_content = md.convert(preview_request.content or '')

    return {
        "title": preview_request.title,
        "date": preview_request.date,
        "content": html_content
    }

@router.get("/{digest_id}/duplicate-detection-status")
def get_duplicate_detection_status(digest_id: int, db: Session = Depends(get_db)):
    """获取快报的重复检测状态"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )

    try:
        status_dict = duplicate_detector_service.get_duplicate_detection_status(digest_id, db)
        return {
            "digest_id": digest_id,
            "detection_status": digest.duplicate_detection_status,
            "duplicate_detection_results": status_dict
        }
    except Exception as e:
        logger.error(f"获取重复检测状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取重复检测状态失败: {str(e)}"
        )

@router.post("/{digest_id}/retrigger-duplicate-detection")
def retrigger_duplicate_detection(digest_id: int, db: Session = Depends(get_db)):
    """重新触发快报的重复检测"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )

    try:
        # 获取快报中的所有新闻ID
        selected_news_ids = [news.id for news in digest.news_items]

        if not selected_news_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="快报中没有新闻"
            )

        # 清除之前的检测结果
        from app.models.duplicate_detection import DuplicateDetectionResult
        db.query(DuplicateDetectionResult).filter(
            DuplicateDetectionResult.digest_id == digest_id
        ).delete()
        db.commit()

        # 重新启动异步重复检测
        duplicate_detector_service.detect_duplicates_for_digest(
            digest.id, selected_news_ids
        )

        logger.info(f"已重新启动快报 {digest.id} 的重复检测")

        return {
            "message": f"已重新启动快报 {digest_id} 的重复检测",
            "digest_id": digest_id,
            "news_count": len(selected_news_ids)
        }

    except Exception as e:
        db.rollback()
        logger.error(f"重新触发重复检测失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新触发重复检测失败: {str(e)}",
        )

@router.get("/{digest_id}/duplicate-detection-estimate")
def get_duplicate_detection_estimate(digest_id: int, db: Session = Depends(get_db)):
    """获取重复检测时间预估"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )

    try:
        from app.services.duplicate_detection_timer import detection_timer
        estimation = detection_timer.estimate_detection_time(digest_id, db)

        return {
            "digest_id": digest_id,
            "estimation": {
                "total_comparisons": estimation.total_comparisons,
                "estimated_duration_seconds": estimation.estimated_duration,
                "estimated_duration_minutes": round(estimation.estimated_duration / 60, 1),
                "avg_llm_call_time": estimation.avg_llm_call_time,
                "current_news_count": estimation.current_news_count,
                "reference_news_count": estimation.reference_news_count,
                "buffer_factor": estimation.buffer_factor,
                "estimated_completion_time": estimation.estimated_completion_time.isoformat() if estimation.estimated_completion_time else None
            }
        }

    except Exception as e:
        logger.error(f"获取重复检测时间预估失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取时间预估失败: {str(e)}"
        )

@router.get("/{digest_id}/duplicate-detection-progress")
def get_duplicate_detection_progress(digest_id: int, db: Session = Depends(get_db)):
    """获取重复检测进度和剩余时间"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )

    try:
        from app.services.duplicate_detection_timer import detection_timer
        progress = detection_timer.get_current_progress(
            digest_id, db, digest.duplicate_detection_started_at
        )

        return {
            "digest_id": digest_id,
            "detection_status": digest.duplicate_detection_status,
            "started_at": format_datetime_with_tz(digest.duplicate_detection_started_at),
            "progress": {
                "completed_comparisons": progress.completed_comparisons,
                "total_comparisons": progress.total_comparisons,
                "current_progress": progress.current_progress,
                "elapsed_time_seconds": progress.elapsed_time,
                "elapsed_time_minutes": round(progress.elapsed_time / 60, 1),
                "estimated_remaining_time_seconds": progress.estimated_remaining_time,
                "estimated_remaining_time_minutes": round(progress.estimated_remaining_time / 60, 1),
                "estimated_completion_time": progress.estimated_completion_time.isoformat() if progress.estimated_completion_time else None
            }
        }

    except Exception as e:
        logger.error(f"获取重复检测进度失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取检测进度失败: {str(e)}"
        )

@router.post("/{digest_id}/duplicate-detection-simulation")
def simulate_detection_timing(
    digest_id: int,
    current_news_count: int = 10,
    reference_news_count: int = 30,
    db: Session = Depends(get_db)
):
    """模拟检测时间数据（用于测试）"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()

    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )

    try:
        from app.services.duplicate_detection_timer import detection_timer

        # 加载模拟数据
        detection_timer.load_simulation_data(current_news_count, reference_news_count)

        # 获取统计信息
        stats = detection_timer.get_timing_statistics()

        return {
            "digest_id": digest_id,
            "simulation_params": {
                "current_news_count": current_news_count,
                "reference_news_count": reference_news_count
            },
            "timing_statistics": stats,
            "message": f"已加载模拟数据，用于 {current_news_count} 条当前新闻 × {reference_news_count} 条参考新闻的场景"
        }

    except Exception as e:
        logger.error(f"模拟检测时间失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"模拟失败: {str(e)}"
        )