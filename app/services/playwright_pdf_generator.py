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
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--font-render-hinting=none',
                        '--disable-font-subpixel-positioning',
                        '--disable-web-security',
                        '--allow-file-access-from-files'
                    ]
                )
                page = await browser.new_page()
                
                # 设置更好的字体渲染
                await page.emulate_media(media='print')
                
                # 设置页面内容
                await page.set_content(html_content)
                
                # 等待页面加载完成（包括字体和样式）
                await page.wait_for_load_state('networkidle')
                
                # 额外等待，确保字体完全加载
                await page.wait_for_timeout(2000)
                
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
                    display_header_footer=False,
                    prefer_css_page_size=True
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
        # 预处理Markdown内容，规范化缩进以确保正确的嵌套列表结构
        md_content = self._normalize_markdown_indentation(digest.content or '')
        
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
        
        html_content = md.convert(md_content)
        
        # 渲染PDF模板 - 使用Typora GitHub主题样式
        template = template_env.get_template("pdf_github_template_typora.html")
        
        return template.render(
            title=digest.title,
            date=digest.date.strftime('%Y-%m-%d'),
            content=html_content,
            fonts_dir=str(self.fonts_dir)
        )
    
    def _normalize_markdown_indentation(self, md_content):
        """规范化Markdown缩进，确保列表结构正确"""
        import re
        
        lines = md_content.split('\n')
        normalized_lines = []
        
        for line in lines:
            # 检查是否是列表项的子项（以"- "开头，前面有空格）
            if re.match(r'^\s+- ', line):
                # 统一使用4个空格缩进
                content = line.lstrip()  # 移除所有前导空格
                normalized_line = '    ' + content  # 添加4个空格
                normalized_lines.append(normalized_line)
                logger.debug(f"规范化缩进: '{line.rstrip()}' -> '{normalized_line}'")
            else:
                # 其他行保持不变
                normalized_lines.append(line)
        
        result = '\n'.join(normalized_lines)
        logger.debug(f"Markdown缩进规范化完成，处理了 {len(lines)} 行")
        return result

# 创建全局实例
pdf_generator = PlaywrightPDFGenerator()

async def generate_pdf_async(digest):
    """异步生成PDF的便捷函数"""
    return await pdf_generator.generate_pdf(digest)

def generate_pdf(digest):
    """同步生成PDF的便捷函数"""
    return asyncio.run(generate_pdf_async(digest)) 