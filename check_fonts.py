#!/usr/bin/env python3

from app.config.paths import FONTS_DIR
import os
import asyncio
from playwright.async_api import async_playwright

def check_fonts():
    print('=== 字体路径检查 ===')
    print('字体目录:', FONTS_DIR)
    print('字体目录绝对路径:', FONTS_DIR.absolute())
    print('字体目录是否存在:', os.path.exists(FONTS_DIR))
    
    # 检查具体字体文件
    github_fonts_dir = FONTS_DIR / 'github'
    print('GitHub字体目录:', github_fonts_dir)
    print('GitHub字体目录是否存在:', os.path.exists(github_fonts_dir))
    
    if os.path.exists(github_fonts_dir):
        print('\n=== GitHub字体文件列表 ===')
        for font_file in os.listdir(github_fonts_dir):
            font_path = github_fonts_dir / font_file
            print(f'  {font_file}: {font_path.absolute()}')
            print(f'    存在: {os.path.exists(font_path)}')
            print(f'    大小: {os.path.getsize(font_path)} bytes')
    
    # 检查file://协议路径
    print('\n=== file://协议测试 ===')
    test_font_path = f'file://{github_fonts_dir.absolute()}/open-sans-v17-latin-ext_latin-regular.woff2'
    print('测试字体URL:', test_font_path)

async def check_font_availability():
    """检查Playwright浏览器中可用的字体"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 创建一个简单的HTML页面来测试字体
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                .test-font {
                    font-family: "Noto Sans CJK SC", "Source Han Sans SC", "思源黑体";
                    font-size: 20px;
                    margin: 10px;
                }
                .fallback-font {
                    font-family: "Arial", sans-serif;
                    font-size: 20px;
                    margin: 10px;
                }
            </style>
        </head>
        <body>
            <div class="test-font">测试思源黑体字体：每日网安情报速递</div>
            <div class="fallback-font">测试后备字体：每日网安情报速递</div>
        </body>
        </html>
        """
        
        await page.set_content(html_content)
        
        # 获取实际使用的字体信息
        font_info = await page.evaluate("""
            () => {
                const testDiv = document.querySelector('.test-font');
                const fallbackDiv = document.querySelector('.fallback-font');
                
                // 检查计算后的样式
                const testStyle = window.getComputedStyle(testDiv);
                const fallbackStyle = window.getComputedStyle(fallbackDiv);
                
                return {
                    testFontFamily: testStyle.fontFamily,
                    fallbackFontFamily: fallbackStyle.fontFamily,
                    testFontSize: testStyle.fontSize
                };
            }
        """)
        
        print("字体信息检查结果:")
        print(f"测试字体 font-family: {font_info['testFontFamily']}")
        print(f"后备字体 font-family: {font_info['fallbackFontFamily']}")
        print(f"字体大小: {font_info['testFontSize']}")
        
        # 生成一个小的PDF来测试
        await page.pdf(
            path="test_font_check.pdf",
            format='A4',
            print_background=True
        )
        
        await browser.close()
        
        print("\n已生成测试PDF文件: test_font_check.pdf")

if __name__ == '__main__':
    check_fonts()
    asyncio.run(check_font_availability()) 