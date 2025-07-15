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
    
    def __init__(self, use_typora_renderer=False):
        self.pdf_dir = PDF_DIR
        self.fonts_dir = FONTS_DIR
        self.use_typora_renderer = use_typora_renderer
        
        # 如果启用Typora渲染器，初始化它
        if self.use_typora_renderer:
            try:
                from app.typora_render_ext.typora_render_ext import TyporaRendererExt
                self.typora_renderer = TyporaRendererExt(
                    theme_path="app/typora_render_ext/typora-theme",
                    theme_name="github"
                )
                logger.info("Typora渲染器已启用")
            except ImportError as e:
                logger.warning(f"无法导入Typora渲染器，回退到原有渲染器: {e}")
                self.use_typora_renderer = False
                self.typora_renderer = None
    
    async def generate_pdf(self, digest):
        """使用Playwright生成PDF文件"""
        try:
            # 设置文件名
            date_str = digest.date.strftime('%Y%m%d')
            file_name = f"每日网安情报速递【{date_str}】_{digest.id}.pdf"
            pdf_path = self.pdf_dir / file_name
            
            # 创建HTML内容
            html_content = self._create_html_content(digest)
            
            # 使用Playwright生成PDF
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-web-security',
                        '--allow-file-access-from-files',
                        '--force-color-profile=srgb',              # 使用sRGB颜色空间
                        '--font-render-hinting=none',              # 苹果风格：不破坏字体原始设计
                        '--enable-font-antialiasing',              # 启用字体抗锯齿
                        '--enable-font-subpixel-positioning',      # 苹果风格：启用亚像素定位
                        '--enable-lcd-text',                       # 启用LCD文本渲染
                        '--force-device-scale-factor=1.0',         # 确保设备缩放为1.0
                        '--enable-precise-memory-info',            # 启用精确内存信息
                        '--disable-background-timer-throttling',   # 禁用后台计时器节流
                        '--disable-renderer-backgrounding',        # 禁用渲染器后台运行
                        '--disable-backgrounding-occluded-windows' # 禁用被遮挡窗口的后台运行
                    ]
                )
                page = await browser.new_page()
                
                # 设置更好的字体渲染 - 模拟苹果系统环境
                await page.emulate_media(media='print')
                
                # 模拟高DPI显示器环境（苹果系统特色）
                await page.set_viewport_size({'width': 1680, 'height': 1050})
                
                # 注入苹果风格的字体渲染优化CSS
                await page.add_style_tag(content='''
                    * {
                        -webkit-font-smoothing: subpixel-antialiased !important;
                        -moz-osx-font-smoothing: auto !important;
                        text-rendering: optimizeQuality !important;
                        font-kerning: auto !important;
                        font-variant-ligatures: common-ligatures contextual !important;
                        font-feature-settings: "kern" 1, "liga" 1, "calt" 1, "onum" 0 !important;
                        font-synthesis: none !important;
                    }
                    
                    body {
                        /* 苹果系统的标准文字间距调整 */
                        letter-spacing: 0.01em !important;
                        word-spacing: 0.02em !important;
                        /* 更紧凑的行间距以容纳更多内容 */
                        line-height: 1.5 !important;
                    }
                    
                    h1, h2, h3, h4, h5, h6 {
                        /* 标题的微调间距 */
                        letter-spacing: 0.005em !important;
                        /* 标题采用更紧密的行间距 */
                        line-height: 1.2 !important;
                        /* 减少标题的上下边距 */
                        margin-top: 0.8em !important;
                        margin-bottom: 0.5em !important;
                    }
                    
                    p, li {
                        /* 段落和列表项的苹果风格间距 */
                        text-align: justify !important;
                        text-justify: auto !important;
                        /* 中英文混排的优化 */
                        hyphens: auto !important;
                        word-break: break-word !important;
                        /* 减少段落间距以容纳更多内容 */
                        margin-top: 0.3em !important;
                        margin-bottom: 0.3em !important;
                    }
                    
                    /* 优化列表间距 */
                    ul, ol {
                        margin-top: 0.5em !important;
                        margin-bottom: 0.5em !important;
                        padding-left: 1.5em !important;
                    }
                    
                    li {
                        margin-bottom: 0.2em !important;
                    }
                    
                    /* 优化分割线样式 */
                    hr {
                        margin: 1em 0 !important;
                        border: none !important;
                        border-top: 2px solid #e7e7e7 !important;
                    }
                ''')
                
                # 设置页面内容
                await page.set_content(html_content)
                
                # 等待页面加载完成（包括字体和样式）
                await page.wait_for_load_state('networkidle')
                
                # 额外等待，确保字体完全加载
                await page.wait_for_timeout(2000)
                
                # 获取页面内容的实际高度
                content_height = await page.evaluate('''
                    () => {
                        return Math.max(
                            document.body.scrollHeight,
                            document.body.offsetHeight,
                            document.documentElement.clientHeight,
                            document.documentElement.scrollHeight,
                            document.documentElement.offsetHeight
                        );
                    }
                ''')
                
                # 增加更多缓冲区高度以容纳更多内容，减少分页
                total_height = content_height + 500  # 增加500px的缓冲区（原来是200px）
                
                logger.info(f"页面内容高度: {content_height}px, 最终PDF高度: {total_height}px")
                
                # 生成PDF - 使用自定义尺寸以容纳所有内容
                await page.pdf(
                    path=str(pdf_path),
                    width='21cm',  # A4宽度保持不变
                    height=f'{total_height}px',  # 动态计算的高度，现在会更高
                    margin={
                        'top': '1cm',    # 减少顶部边距（原来1.5cm）
                        'right': '1.5cm', # 减少右边距（原来2cm）
                        'bottom': '1cm',  # 减少底部边距（原来2cm）
                        'left': '1.5cm'   # 减少左边距（原来2cm）
                    },
                    print_background=True,
                    display_header_footer=False,
                    prefer_css_page_size=False  # 禁用CSS页面尺寸，使用我们自定义的尺寸
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
        if self.use_typora_renderer and self.typora_renderer:
            # 使用Typora渲染器
            try:
                logger.info("使用Typora渲染器生成HTML内容")
                html_content = self.typora_renderer.render_string(
                    markdown_string=digest.content or '',
                    title=digest.title or '',
                    lang="zh-CN"
                )
                return html_content
            except Exception as e:
                logger.error(f"Typora渲染器失败，回退到原有渲染器: {e}")
                # 回退到原有渲染器
                return self._create_html_content_legacy(digest)
        else:
            # 使用原有渲染器
            return self._create_html_content_legacy(digest)
    
    def _create_html_content_legacy(self, digest):
        """原有的HTML内容生成方法（向后兼容）"""
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

# 创建全局实例 - 默认使用原有渲染器保证兼容性
pdf_generator = PlaywrightPDFGenerator(use_typora_renderer=False)

# 创建Typora版本的实例供选择使用
pdf_generator_typora = PlaywrightPDFGenerator(use_typora_renderer=True)

async def generate_pdf_async(digest):
    """异步生成PDF的便捷函数（原有渲染器）"""
    return await pdf_generator.generate_pdf(digest)

def generate_pdf(digest):
    """同步生成PDF的便捷函数（原有渲染器）"""
    return asyncio.run(generate_pdf_async(digest))

async def generate_pdf_typora_async(digest):
    """异步生成PDF的便捷函数（Typora渲染器）"""
    return await pdf_generator_typora.generate_pdf(digest)

def generate_pdf_typora(digest):
    """同步生成PDF的便捷函数（Typora渲染器）"""
    return asyncio.run(generate_pdf_typora_async(digest)) 