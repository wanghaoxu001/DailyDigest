import os
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from pathlib import Path
import asyncio
import markdown
from markdown.extensions import codehilite, tables, toc

# 获取日志记录器
from app.config import get_logger
from app.config.paths import PDF_DIR, FONTS_DIR, TEMPLATES_DIR, get_pdf_relative_path

logger = get_logger(__name__)

# 加载模板引擎
template_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

class PlaywrightPDFGenerator:
    """基于Playwright的PDF生成器"""
    
    def __init__(self):
        self.pdf_dir = PDF_DIR
        self.fonts_dir = FONTS_DIR
    
    async def generate_pdf(self, digest):
        """使用Playwright生成PDF文件"""
        try:
            # 设置文件名
            file_name = f"digest_{digest.date.strftime('%Y%m%d')}_{digest.id}.pdf"
            pdf_path = self.pdf_dir / file_name
            
            # 创建HTML内容
            html_content = self._create_html_content(digest)
            
            # 使用Playwright生成PDF
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 设置页面内容
                await page.set_content(html_content)
                
                # 等待页面加载完成（包括字体和样式）
                await page.wait_for_load_state('networkidle')
                
                # 生成PDF
                await page.pdf(
                    path=str(pdf_path),
                    format='A4',
                    margin={
                        'top': '1.5cm',
                        'right': '2cm', 
                        'bottom': '2cm',
                        'left': '2cm'
                    },
                    print_background=True,
                    display_header_footer=False
                )
                
                await browser.close()
            
            # 返回相对路径（用于存储和访问）
            rel_path = get_pdf_relative_path(file_name)
            logger.info(f"PDF已生成: {rel_path}")
            
            return rel_path
            
        except Exception as e:
            logger.error(f"生成PDF失败: {str(e)}")
            return None
    
    def _create_html_content(self, digest):
        """创建用于PDF生成的HTML内容"""
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
        
        html_content = md.convert(digest.content or '')
        
        # 渲染PDF模板
        template = template_env.get_template("pdf_github_template.html")
        
        return template.render(
            title=digest.title,
            date=digest.date.strftime('%Y-%m-%d'),
            content=html_content,
            fonts_dir=str(self.fonts_dir)
        )

# 创建全局实例
pdf_generator = PlaywrightPDFGenerator()

async def generate_pdf_async(digest):
    """异步生成PDF的便捷函数"""
    return await pdf_generator.generate_pdf(digest)

def generate_pdf(digest):
    """同步生成PDF的便捷函数"""
    return asyncio.run(generate_pdf_async(digest)) 