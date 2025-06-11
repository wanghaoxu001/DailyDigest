from fastapi import APIRouter, Depends, HTTPException, status, Response
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
    
    for key, value in update_data.items():
        setattr(digest, key, value)
    
    db.commit()
    db.refresh(digest)
    
    # 手动转换ORM对象到字典
    return digest_to_dict(digest)

@router.post("/{digest_id}/generate-pdf", response_model=DigestResponse)
def generate_digest_pdf(digest_id: int, db: Session = Depends(get_db)):
    """生成快报的PDF文件"""
    digest = db.query(Digest).filter(Digest.id == digest_id).first()
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="快报不存在"
        )
    
    # 生成PDF
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

@router.get("/{digest_id}/pdf")
def download_digest_pdf(digest_id: int, db: Session = Depends(get_db)):
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
    
    # 返回文件作为响应
    try:
        with open(pdf_absolute_path, "rb") as file:
            content = file.read()
        
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=digest_{digest.date.strftime('%Y%m%d')}.pdf"
            }
        )
    except Exception as e:
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