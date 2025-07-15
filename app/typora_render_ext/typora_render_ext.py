#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Typora风格Markdown渲染器（扩展版）
提供更多自定义选项和渲染优化
"""

import os
import re
import sys
import argparse
import markdown
from bs4 import BeautifulSoup
import shutil
import hashlib
from typing import List, Dict, Any, Optional, Union

class TyporaRendererExt:
    """Typora风格Markdown渲染器（扩展版）"""
    
    def __init__(self, theme_path="typora-theme", theme_name="github", custom_css=None):
        """
        初始化渲染器
        
        Args:
            theme_path: Typora主题文件夹路径
            theme_name: 主题名称，默认为github
            custom_css: 自定义CSS内容，将附加到主题CSS之后
        """
        self.theme_path = theme_path
        self.theme_name = theme_name
        self.css_file = os.path.join(theme_path, f"{theme_name}.css")
        self.theme_assets_dir = os.path.join(theme_path, theme_name)
        self.custom_css = custom_css
        
        # 读取CSS内容
        try:
            with open(self.css_file, 'r', encoding='utf-8') as f:
                self.css_content = f.read()
                
            # 附加自定义CSS
            if self.custom_css:
                self.css_content += f"\n\n/* 自定义CSS */\n{self.custom_css}"
                
        except FileNotFoundError:
            print(f"错误: 找不到CSS文件: {self.css_file}")
            sys.exit(1)
        
        # 内部缓存处理过的HTML，避免重复处理
        self._html_cache = {}
    
    def _get_html_template(self, title, lang="zh-CN"):
        """
        生成HTML模板
        
        Args:
            title: HTML文档标题
            lang: HTML文档语言
            
        Returns:
            包含所有CSS样式的HTML模板字符串
        """
        # 修复CSS内容中的格式化问题
        # 处理可能导致str.format()问题的大括号字符
        safe_css_content = self.css_content.replace("{", "{{").replace("}", "}}")
        
        return f'''<!doctype html>
<html lang="{lang}">
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width initial-scale=1'>
<title>{title}</title>
<style type='text/css'>
{safe_css_content}
</style>
</head>
<body class='typora-export'>
<div class='typora-export-content'>
<div id='write' class=''>
{{content}}
</div>
</div>
</body>
</html>'''

    def _process_html_content(self, html_content):
        """
        处理HTML内容，优化样式和结构
        
        Args:
            html_content: 原始HTML内容
            
        Returns:
            处理后的HTML内容
        """
        # 使用缓存避免重复处理相同的HTML
        content_hash = hashlib.md5(html_content.encode()).hexdigest()
        if content_hash in self._html_cache:
            return self._html_cache[content_hash]
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 处理特殊情况：强调文本（** **）
        strong_tags = soup.find_all('strong')
        for tag in strong_tags:
            if tag.parent.name != 'span':
                tag.wrap(soup.new_tag('span'))
        
        # 处理所有标题
        heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        for tag in heading_tags:
            # 为标题添加ID属性，用于锚点链接
            if not tag.get('id'):
                tag_id = re.sub(r'[^\w\- ]', '', tag.text)
                tag_id = re.sub(r'\s+', '-', tag_id).lower()
                tag['id'] = tag_id
            
            # 处理标题中的强调文本
            strong_tags = tag.find_all('strong')
            for strong in strong_tags:
                if strong.parent.name != 'span':
                    strong.wrap(soup.new_tag('span'))
        
        # 处理有序列表和无序列表中的嵌套结构
        ordered_lists = soup.find_all('ol')
        for ol in ordered_lists:
            # 查找直接子元素的列表项
            list_items = ol.find_all('li', recursive=False)
            for i, item in enumerate(list_items):
                if i % 2 == 0 and i+1 < len(list_items):
                    # 检查是否有标题+内容的模式（两个连续li，一个是标题，一个是内容）
                    title_item = item
                    content_item = list_items[i+1]
                    
                    # 检查标题项是否只包含标题
                    if title_item.find('strong') and not content_item.find('strong'):
                        # 创建无序列表包装内容项
                        ul_tag = soup.new_tag('ul')
                        # 将内容项移到标题项下的无序列表中
                        content_item.extract()  # 从原位置移除
                        ul_tag.append(content_item)  # 添加到无序列表
                        title_item.append(ul_tag)   # 将无序列表添加到标题项
        
        # 继续处理其他列表项
        list_items = soup.find_all('li')
        for item in list_items:
            # 确保列表项内的段落正确嵌套
            p_tags = item.find_all('p', recursive=False)
            for p in p_tags:
                # 确保段落中的强调文本正确嵌套
                strong_tags = p.find_all('strong')
                for strong in strong_tags:
                    if strong.parent.name != 'span':
                        strong.wrap(soup.new_tag('span'))
        
        # 处理引用块
        blockquotes = soup.find_all('blockquote')
        for quote in blockquotes:
            p_tags = quote.find_all('p')
            for p in p_tags:
                # 确保引用块中的文本正确嵌套
                if p.string and not p.find('span'):
                    p.string.wrap(soup.new_tag('span'))
                
                # 处理引用块中的强调文本
                strong_tags = p.find_all('strong')
                for strong in strong_tags:
                    if strong.parent.name != 'span':
                        strong.wrap(soup.new_tag('span'))
        
        # 处理代码块
        code_blocks = soup.find_all('pre')
        for pre in code_blocks:
            code = pre.find('code')
            if code:
                # 确保代码块有正确的类名
                class_name = code.get('class', [])
                if class_name and any('language-' in c for c in class_name):
                    # 已经有语言标识，不需要额外处理
                    pass
                else:
                    # 尝试添加默认语言类
                    code['class'] = class_name + ['language-plaintext']
        
        # 处理表格
        tables = soup.find_all('table')
        for table in tables:
            # 确保表格有正确的类名
            if not table.get('class'):
                table['class'] = ['table']
        
        # 处理链接
        links = soup.find_all('a')
        for link in links:
            if not link.get('target'):
                link['target'] = '_blank'
            if not link.get('rel'):
                link['rel'] = 'noopener noreferrer'
        
        processed_html = str(soup)
        self._html_cache[content_hash] = processed_html
        return processed_html

    def render(self, 
               markdown_file: str, 
               output_file: Optional[str] = None, 
               copy_assets: bool = True,
               lang: str = "zh-CN",
               extensions: Optional[List[str]] = None) -> str:
        """
        渲染Markdown文件为HTML
        
        Args:
            markdown_file: Markdown文件路径
            output_file: 输出HTML文件路径，默认为与Markdown文件同名但扩展名为.html
            copy_assets: 是否复制主题资源文件到输出目录
            lang: HTML文档语言
            extensions: 额外的Markdown扩展列表
            
        Returns:
            输出HTML文件的路径
        """
        # 如果没有指定输出文件，则使用默认名称
        if output_file is None:
            output_file = os.path.splitext(markdown_file)[0] + '.html'
        
        # 读取Markdown内容
        try:
            with open(markdown_file, 'r', encoding='utf-8') as f:
                md_content = f.read()
        except FileNotFoundError:
            print(f"错误: 找不到Markdown文件: {markdown_file}")
            sys.exit(1)
        
        # 提取文件标题（使用文件名或第一个标题）
        title = os.path.basename(os.path.splitext(markdown_file)[0])
        title_match = re.search(r'^#\s+(.+)$', md_content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip('*# ')
        
        # 默认扩展列表
        default_extensions = [
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
            'markdown.extensions.nl2br',
            'markdown.extensions.attr_list',
            'markdown.extensions.def_list',
            'markdown.extensions.abbr',
            'markdown.extensions.footnotes',
            'markdown.extensions.md_in_html',
            'markdown.extensions.toc'
        ]
        
        # 合并默认扩展和用户提供的扩展
        if extensions:
            for ext in extensions:
                if ext not in default_extensions:
                    default_extensions.append(ext)
        
        # 转换Markdown为HTML
        html_content = markdown.markdown(
            md_content,
            extensions=default_extensions
        )
        
        # 处理HTML内容
        processed_html = self._process_html_content(html_content)
        
        # 使用模板生成完整HTML
        template = self._get_html_template(title, lang)
        full_html = template.format(content=processed_html)
        
        # 写入输出文件
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        # 如果需要，复制主题资产文件
        if copy_assets and os.path.exists(self.theme_assets_dir):
            assets_dir = os.path.join(output_dir or os.path.dirname(output_file), self.theme_name)
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)
            
            # 复制主题文件夹中的所有文件
            for file in os.listdir(self.theme_assets_dir):
                src = os.path.join(self.theme_assets_dir, file)
                dst = os.path.join(assets_dir, file)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
        
        return output_file
    
    def render_string(self, 
                      markdown_string: str, 
                      title: str = "Markdown Document",
                      lang: str = "zh-CN",
                      extensions: Optional[List[str]] = None) -> str:
        """
        直接渲染Markdown字符串为HTML字符串
        
        Args:
            markdown_string: Markdown字符串
            title: HTML文档标题
            lang: HTML文档语言
            extensions: 额外的Markdown扩展列表
            
        Returns:
            HTML字符串
        """
        # 提取第一个标题作为文档标题（如果有）
        title_match = re.search(r'^#\s+(.+)$', markdown_string, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip('*# ')
        
        # 默认扩展列表
        default_extensions = [
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.codehilite',
            'markdown.extensions.nl2br',
            'markdown.extensions.attr_list',
            'markdown.extensions.def_list',
            'markdown.extensions.abbr',
            'markdown.extensions.footnotes',
            'markdown.extensions.md_in_html',
            'markdown.extensions.toc'
        ]
        
        # 合并默认扩展和用户提供的扩展
        if extensions:
            for ext in extensions:
                if ext not in default_extensions:
                    default_extensions.append(ext)
        
        # 转换Markdown为HTML
        html_content = markdown.markdown(
            markdown_string,
            extensions=default_extensions
        )
        
        # 处理HTML内容
        processed_html = self._process_html_content(html_content)
        
        # 使用模板生成完整HTML
        template = self._get_html_template(title, lang)
        full_html = template.format(content=processed_html)
        
        return full_html

def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(description='将Markdown文件按照Typora样式渲染为HTML(扩展版)')
    parser.add_argument('input', help='输入Markdown文件路径')
    parser.add_argument('-o', '--output', help='输出HTML文件路径')
    parser.add_argument('-t', '--theme-path', default='typora-theme', help='Typora主题文件夹路径')
    parser.add_argument('-n', '--theme-name', default='github', help='主题名称')
    parser.add_argument('-l', '--lang', default='zh-CN', help='文档语言')
    parser.add_argument('--custom-css', help='自定义CSS文件路径')
    parser.add_argument('--no-assets', action='store_true', help='不复制主题资源文件')
    
    args = parser.parse_args()
    
    # 读取自定义CSS（如果有）
    custom_css = None
    if args.custom_css:
        try:
            with open(args.custom_css, 'r', encoding='utf-8') as f:
                custom_css = f.read()
        except FileNotFoundError:
            print(f"警告: 找不到自定义CSS文件: {args.custom_css}")
    
    renderer = TyporaRendererExt(
        theme_path=args.theme_path,
        theme_name=args.theme_name,
        custom_css=custom_css
    )
    
    output_file = renderer.render(
        markdown_file=args.input, 
        output_file=args.output, 
        copy_assets=not args.no_assets,
        lang=args.lang
    )
    
    print(f"成功将 {args.input} 渲染为 {output_file}")

if __name__ == '__main__':
    main() 