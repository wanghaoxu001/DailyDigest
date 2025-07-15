from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime, date
import os
import markdown

from app.db.session import get_db
from app.models.digest import Digest
from app.models.news import News, NewsCategory
from app.services.digest_generator import create_digest_content, generate_pdf
from app.api.endpoints.news import news_to_dict
from app.config.paths import get_pdf_absolute_path
from app.config import get_logger

logger = get_logger(__name__)

router = APIRouter()

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
        "date": digest.date.isoformat() if digest.date else None,
        "content": digest.content,
        "pdf_path": digest.pdf_path,
        "news_counts": digest.news_counts,
        "created_at": digest.created_at.isoformat() if digest.created_at else None
    }

def digest_detail_to_dict(digest: Digest) -> dict:
    """将数据库Digest模型转换为详细响应字典，包括关联的新闻"""
    # 基本信息
    digest_dict = digest_to_dict(digest)
    
    # 添加关联的新闻条目
    news_items = []
    for news in digest.news_items:
        news_items.append({
            "id": news.id,
            "title": news.title,
            "generated_title": news.generated_title or "",
            "generated_summary": news.generated_summary or "",
            "category": news.category.value if news.category else "其他"
        })
    
    digest_dict["news_items"] = news_items
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
    
    # 关联新闻
    digest.news_items = selected_news
    
    # 标记所有相关新闻为已使用
    for news in selected_news:
        news.is_used_in_digest = True
    
    db.add(digest)
    db.commit()
    db.refresh(digest)
    
    # 手动转换ORM对象到字典
    return digest_to_dict(digest)

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
    return digest_detail_to_dict(digest)

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
    
    for key, value in update_data.items():
        setattr(digest, key, value)
    
    db.commit()
    db.refresh(digest)
    
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
    digest.pdf_path = pdf_path
    db.commit()
    db.refresh(digest)
    
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