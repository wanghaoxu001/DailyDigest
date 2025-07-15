"""
统一路径管理配置
提供跨平台兼容的路径处理
"""
from pathlib import Path
import os

# 应用根目录（项目根目录）
APP_ROOT = Path(__file__).parent.parent.parent.absolute()

# 应用代码目录
APP_DIR = APP_ROOT / "app"

# 静态文件目录
STATIC_DIR = APP_DIR / "static"

# PDF文件目录
PDF_DIR = STATIC_DIR / "pdf"

# 模板目录
TEMPLATES_DIR = APP_DIR / "templates"

# 字体目录
FONTS_DIR = STATIC_DIR / "fonts"

# 日志目录
LOGS_DIR = APP_ROOT / "logs"

# 数据库文件路径
DATABASE_PATH = APP_ROOT / "daily_digest.db"

def ensure_directories():
    """确保所有必要的目录存在"""
    directories = [STATIC_DIR, PDF_DIR, TEMPLATES_DIR, FONTS_DIR, LOGS_DIR]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

def get_pdf_absolute_path(relative_path: str) -> Path:
    """
    将PDF相对路径转换为绝对路径
    
    Args:
        relative_path: 形如 "static/pdf/每日网安情报速递【20250611】_7.pdf" 的相对路径
        
    Returns:
        绝对路径Path对象
    """
    if Path(relative_path).is_absolute():
        return Path(relative_path)
    
    # 处理以static/开头的相对路径
    if relative_path.startswith("static/"):
        return APP_DIR / relative_path
    
    # 如果不是以static/开头，假设是PDF文件名
    return PDF_DIR / relative_path

def get_pdf_relative_path(pdf_filename: str) -> str:
    """
    生成PDF文件的相对路径（用于数据库存储）
    
    Args:
        pdf_filename: PDF文件名，如 "每日网安情报速递【20250611】_7.pdf"
        
    Returns:
        相对路径字符串，如 "static/pdf/每日网安情报速递【20250611】_7.pdf"
    """
    return f"static/pdf/{pdf_filename}"

def get_template_path(template_name: str) -> Path:
    """获取模板文件的绝对路径"""
    return TEMPLATES_DIR / template_name

# 在模块加载时确保目录存在
ensure_directories() 