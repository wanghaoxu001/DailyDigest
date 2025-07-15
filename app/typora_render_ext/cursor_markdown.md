# 如何在其他项目中使用markdown模块
_Exported on 2025/6/19 at GMT+8 21:54:04 from Cursor (1.1.3)_

---

**User**

如果我想在其他项目中使用这个模块来将markdown渲染为html文件，我还需要移植哪些文件？如何使用？

---

**Cursor**

我来帮你分析一下如何在其他项目中使用这个Markdown渲染模块。

基于我对代码的分析，要在其他项目中使用这个Typora风格的Markdown渲染器，你需要移植以下文件：

## 必需文件

### 1. 核心模块
```
typora_render_ext.py  # 主要的渲染器模块
```

### 2. 主题文件
```
typora-theme/
├── github.css                                           # 主题CSS样式文件
└── github/                                              # 字体资源文件夹
    ├── open-sans-v17-latin-ext_latin-700.woff2
    ├── open-sans-v17-latin-ext_latin-700italic.woff2
    ├── open-sans-v17-latin-ext_latin-italic.woff2
    └── open-sans-v17-latin-ext_latin-regular.woff2
```

## Python依赖

需要安装以下Python包：

```bash
pip install markdown>=3.3.6 beautifulsoup4>=4.10.0
```

或者创建一个简化的 `requirements.txt`：
```
markdown>=3.3.6
beautifulsoup4>=4.10.0
```

## 使用方法

### 1. 命令行使用

```bash
# 基本用法
python typora_render_ext.py input.md

# 指定输出文件
python typora_render_ext.py input.md -o output.html

# 使用自定义主题路径
python typora_render_ext.py input.md -t /path/to/typora-theme -n github

# 添加自定义CSS
python typora_render_ext.py input.md --custom-css custom.css

# 不复制字体资源文件（减小输出文件夹大小）
python typora_render_ext.py input.md --no-assets
```

### 2. Python代码中使用

```python
from typora_render_ext import TyporaRendererExt

# 创建渲染器实例
renderer = TyporaRendererExt(
    theme_path="typora-theme",  # 主题文件夹路径
    theme_name="github",        # 主题名称
    custom_css=None            # 可选的自定义CSS
)

# 方法1: 渲染Markdown文件
output_file = renderer.render(
    markdown_file="input.md",
    output_file="output.html",   # 可选，默认与输入文件同名
    copy_assets=True,           # 是否复制字体文件
    lang="zh-CN"               # HTML文档语言
)

# 方法2: 直接渲染Markdown字符串
markdown_content = "# 标题\n\n这是一段**粗体**文本。"
html_string = renderer.render_string(
    markdown_string=markdown_content,
    title="我的文档",
    lang="zh-CN"
)

print(html_string)  # 输出完整的HTML字符串
```

### 3. 高级配置

```python
# 使用自定义CSS
custom_css = """
body { background-color: #f5f5f5; }
h1 { color: #2c3e50; }
"""

renderer = TyporaRendererExt(
    theme_path="typora-theme",
    theme_name="github", 
    custom_css=custom_css
)

# 添加自定义Markdown扩展
additional_extensions = [
    'markdown.extensions.smarty',  # 智能标点
    'markdown.extensions.sane_lists'  # 更好的列表处理
]

html_output = renderer.render_string(
    markdown_string=markdown_content,
    extensions=additional_extensions
)
```

## 项目结构建议

在你的新项目中建议采用以下结构：

```
your_project/
├── typora_render_ext.py      # 渲染器模块
├── typora-theme/             # 主题文件夹
│   ├── github.css
│   └── github/
│       ├── open-sans-v17-latin-ext_latin-700.woff2
│       ├── open-sans-v17-latin-ext_latin-700italic.woff2
│       ├── open-sans-v17-latin-ext_latin-italic.woff2
│       └── open-sans-v17-latin-ext_latin-regular.woff2
├── requirements.txt          # Python依赖
└── your_script.py           # 你的主程序
```

## 注意事项

1. **字体文件可选**：如果不需要完全一致的字体效果，可以只复制 `typora_render_ext.py` 和 `github.css`，字体会回退到系统默认字体。

2. **相对路径**：确保主题文件夹的相对路径正确，或者在创建渲染器时指定绝对路径。

3. **输出目录**：渲染器会自动创建输出目录（如果不存在）。

4. **缓存机制**：模块内置了HTML处理缓存，重复渲染相同内容时会更快。

这样你就可以在任何Python项目中轻松使用这个Typora风格的Markdown渲染器了！

```plaintext
typora_render_ext.py  # 主要的渲染器模块
```

```plaintext
typora-theme/
├── github.css                                           # 主题CSS样式文件
└── github/                                              # 字体资源文件夹
    ├── open-sans-v17-latin-ext_latin-700.woff2
    ├── open-sans-v17-latin-ext_latin-700italic.woff2
    ├── open-sans-v17-latin-ext_latin-italic.woff2
    └── open-sans-v17-latin-ext_latin-regular.woff2
```

```shellscript
pip install markdown>=3.3.6 beautifulsoup4>=4.10.0
```

```plaintext
markdown>=3.3.6
beautifulsoup4>=4.10.0
```

```shellscript
# 基本用法
python typora_render_ext.py input.md

# 指定输出文件
python typora_render_ext.py input.md -o output.html

# 使用自定义主题路径
python typora_render_ext.py input.md -t /path/to/typora-theme -n github

# 添加自定义CSS
python typora_render_ext.py input.md --custom-css custom.css

# 不复制字体资源文件（减小输出文件夹大小）
python typora_render_ext.py input.md --no-assets
```

```python
from typora_render_ext import TyporaRendererExt

# 创建渲染器实例
renderer = TyporaRendererExt(
    theme_path="typora-theme",  # 主题文件夹路径
    theme_name="github",        # 主题名称
    custom_css=None            # 可选的自定义CSS
)

# 方法1: 渲染Markdown文件
output_file = renderer.render(
    markdown_file="input.md",
    output_file="output.html",   # 可选，默认与输入文件同名
    copy_assets=True,           # 是否复制字体文件
    lang="zh-CN"               # HTML文档语言
)

# 方法2: 直接渲染Markdown字符串
markdown_content = "# 标题\n\n这是一段**粗体**文本。"
html_string = renderer.render_string(
    markdown_string=markdown_content,
    title="我的文档",
    lang="zh-CN"
)

print(html_string)  # 输出完整的HTML字符串
```

```python
# 使用自定义CSS
custom_css = """
body { background-color: #f5f5f5; }
h1 { color: #2c3e50; }
"""

renderer = TyporaRendererExt(
    theme_path="typora-theme",
    theme_name="github", 
    custom_css=custom_css
)

# 添加自定义Markdown扩展
additional_extensions = [
    'markdown.extensions.smarty',  # 智能标点
    'markdown.extensions.sane_lists'  # 更好的列表处理
]

html_output = renderer.render_string(
    markdown_string=markdown_content,
    extensions=additional_extensions
)
```

```plaintext
your_project/
├── typora_render_ext.py      # 渲染器模块
├── typora-theme/             # 主题文件夹
│   ├── github.css
│   └── github/
│       ├── open-sans-v17-latin-ext_latin-700.woff2
│       ├── open-sans-v17-latin-ext_latin-700italic.woff2
│       ├── open-sans-v17-latin-ext_latin-italic.woff2
│       └── open-sans-v17-latin-ext_latin-regular.woff2
├── requirements.txt          # Python依赖
└── your_script.py           # 你的主程序
```

