# HTML内容清理功能实现

## 问题描述

在新闻文章抓取过程中，summary和content字段经常包含HTML标记，这会在前端显示时造成错误。例如：

```html
"summary": "<p>With crime-as-a-service lowering the barrier to entry and prosecution lagging behind, enterprise security teams must rethink their strategies to detect and disrupt scams at scale.</p>\n<p>The post <a href=\"https://www.securityweek.com/why-scamming-cant-be-stopped-but-it-can-be-managed/\">Why Scamming Can&#8217;t Be Stopped—But It Can Be Managed</a> appeared first on <a href=\"https://www.securityweek.com\">SecurityWeek</a>.</p>"
```

这种HTML标记会导致前端显示异常，用户体验不佳。

## 解决方案

### 1. 实现HTML清理函数

在 `app/services/crawler.py` 中添加了专门的HTML清理功能：

```python
# 创建专门用于清理HTML标记的转换器
html_cleaner = html2text.HTML2Text()
html_cleaner.ignore_links = True
html_cleaner.ignore_images = True
html_cleaner.ignore_emphasis = True
html_cleaner.ignore_tables = True
html_cleaner.unicode_snob = True
html_cleaner.body_width = 0  # 不进行换行
html_cleaner.use_automatic_links = False

def clean_html_content(content: str) -> str:
    """
    清理HTML标记，返回纯文本内容
    """
    if not content:
        return content
    
    try:
        # 使用html2text清理HTML标记
        cleaned = html_cleaner.handle(content)
        
        # 清理多余的换行符和空格
        cleaned = re.sub(r'\n\s*\n', '\n', cleaned)  # 移除多余的空行
        cleaned = re.sub(r'\n+', ' ', cleaned)  # 将换行转换为空格
        cleaned = re.sub(r'\s+', ' ', cleaned)  # 合并多个空格
        cleaned = cleaned.strip()
        
        # 移除残留的特殊字符
        cleaned = re.sub(r'&#\d+;', '', cleaned)  # 移除HTML实体编码
        cleaned = re.sub(r'&[a-zA-Z]+;', '', cleaned)  # 移除HTML实体名称
        
        return cleaned
    except Exception as e:
        logger.warning(f"清理HTML内容失败: {str(e)}")
        # 如果清理失败，至少尝试移除基本的HTML标签
        return re.sub(r'<[^>]+>', '', content)
```

### 2. 在数据处理流程中应用清理

在所有返回文章数据的关键位置应用HTML清理：

#### A. Newspaper4k处理结果清理
```python
# 在 _get_content_with_newspaper4k 函数的返回处
return {
    "parsed_title": parsed_title,
    "content": clean_html_content(text_content),
    "summary": clean_html_content(summary),
    "publish_date": publish_date,
    "keywords": keywords,
    "original_url": article_url,
}
```

#### B. RSS内容直接使用时的清理
```python
# 在 get_rss_entry_article_data 函数中不使用Newspaper4k时
return {
    "title": feed_entry.title,
    "summary": clean_html_content(summary),
    "content": clean_html_content(content),
    "original_url": feed_entry.link,
    "publish_date": publish_date,
    "newspaper_keywords": [],
    "entities": {},
    "is_processed": False,
}
```

#### C. 微信文章解析结果的清理
```python
# 在微信文章特定解析器返回的数据中
{
    "title": item_title,
    "summary": clean_html_content(summary),
    "content": clean_html_content(content),
    "original_url": wechat_url,
    "publish_date": pub_date,
    "newspaper_keywords": [],
    "entities": entities,
    "is_processed": False,
}
```

## 功能特点

### 1. 智能HTML清理
- 使用 `html2text` 库进行专业的HTML到文本转换
- 配置忽略链接、图片、强调标记等，确保输出纯文本
- 智能处理HTML实体编码（如 `&#8217;`、`&amp;` 等）

### 2. 文本格式优化
- 自动移除多余的换行符和空格
- 将换行符转换为空格，提高可读性
- 合并连续的空格字符

### 3. 错误容错处理
- 如果html2text处理失败，回退到基本的正则表达式清理
- 对空值和None值进行安全处理
- 记录清理失败的日志信息

### 4. 性能优化
- 只在必要时进行清理，避免重复处理
- 使用预配置的html2text实例，减少初始化开销

## 测试验证

### 测试用例1：段落和链接
**输入:**
```html
<p>With crime-as-a-service lowering the barrier to entry and prosecution lagging behind, enterprise security teams must rethink their strategies to detect and disrupt scams at scale.</p>
<p>The post <a href="https://www.securityweek.com/why-scamming-cant-be-stopped-but-it-can-be-managed/">Why Scamming Can&#8217;t Be Stopped—But It Can Be Managed</a> appeared first on <a href="https://www.securityweek.com">SecurityWeek</a>.</p>
```

**输出:**
```
With crime-as-a-service lowering the barrier to entry and prosecution lagging behind, enterprise security teams must rethink their strategies to detect and disrupt scams at scale. The post Why Scamming Can't Be Stopped—But It Can Be Managed appeared first on SecurityWeek.
```

### 测试用例2：特殊字符和实体编码
**输入:**
```html
<div>Data breach affects <strong>100,000+</strong> users &amp; their personal info.</div>
```

**输出:**
```
Data breach affects 100,000+ users & their personal info.
```

### 测试用例3：复杂嵌套HTML
**输入:**
```html
<article>
    <h1>Security Alert</h1>
    <p>A new <em>malware</em> variant has been discovered targeting <strong>financial institutions</strong>.</p>
    <ul>
        <li>Banking systems</li>
        <li>Payment processors</li>
    </ul>
    <p>Read more at <a href="https://example.com">example.com</a></p>
</article>
```

**输出:**
```
# Security Alert A new malware variant has been discovered targeting financial institutions. * Banking systems * Payment processors Read more at example.com
```

## 效果对比

### 清理前
- 包含各种HTML标签：`<p>`、`<a>`、`<strong>` 等
- HTML实体编码：`&#8217;`、`&amp;` 等
- 前端显示可能出现格式问题或渲染错误

### 清理后
- 纯文本内容，无HTML标记
- 正确处理特殊字符
- 前端显示正常，用户体验良好

## 实施位置

清理功能在数据入库前执行，确保数据库中存储的内容始终是干净的纯文本：

1. **RSS新闻抓取**：在`fetch_rss_feed`处理过程中自动应用
2. **网页新闻抓取**：在`fetch_webpage`处理过程中自动应用  
3. **微信文章处理**：在微信文章解析后自动应用
4. **手动添加新闻**：通过API添加的新闻也会自动清理

## 兼容性

- 对现有数据库中的新闻记录无影响
- 新抓取的内容会自动应用清理
- 不影响LLM处理和其他后续流程
- 保持API接口的向后兼容性

## 维护说明

如需调整清理规则，可以修改`clean_html_content`函数中的正则表达式或html2text配置参数。建议在修改前进行充分测试，确保不影响内容的可读性和完整性。 