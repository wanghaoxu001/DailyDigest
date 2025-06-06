# RSS备选摘要功能实现

## 功能概述

为订阅源添加了一个"使用description作为备选摘要"选项，当RSS条目的summary字段质量不佳时，系统会自动使用description字段作为备选摘要。

## 问题背景

在RSS新闻抓取过程中，部分RSS源的summary字段可能：
- 内容过短（少于50个字符）
- 与标题完全相同
- 质量不佳或缺失

这些情况下，如果RSS条目包含更详细的description字段，使用description作为摘要会提供更好的内容质量。

## 实现方案

### 1. 数据库层面

在`Source`模型中添加新字段：
```python
use_description_as_summary = Column(Boolean, default=False)  # 当没有高质量摘要时，使用description作为备选摘要
```

### 2. API层面

**API模型更新**：
- `SourceBase`、`SourceCreate`、`SourceUpdate`、`SourceResponse`中都添加了`use_description_as_summary`字段
- `source_to_dict`函数中添加了对新字段的处理，包含向后兼容性

**创建和更新操作**：
- 创建新闻源时可以设置备选摘要选项
- 更新新闻源时可以修改备选摘要设置

### 3. 爬虫逻辑

**摘要质量检查**：
```python
# 检查摘要质量（不能太短，不能和标题完全相同）
if len(summary_candidate) > 50 and summary_candidate != feed_entry.title:
    summary = summary_candidate
```

**备选摘要逻辑**：
```python
# 如果没有高质量摘要且启用了备选摘要选项，使用description
if not summary and use_description_as_summary:
    if hasattr(feed_entry, "description") and feed_entry.description:
        description_candidate = feed_entry.description.strip()
        if len(description_candidate) > 20 and description_candidate != feed_entry.title:
            summary = description_candidate
```

**两种处理模式支持**：

1. **直接使用RSS内容模式**（`use_newspaper=False`）：
   - 优先使用高质量的summary
   - 如果启用备选摘要且summary质量不佳，使用description
   - 最后备选：从content生成摘要

2. **使用Newspaper4k模式**（`use_newspaper=True`）：
   - 在传递给Newspaper4k处理前，先检查是否需要使用description
   - 如果需要，创建修改过的feed_entry副本，将description设为summary
   - 让Newspaper4k使用处理后的摘要

### 4. 前端界面

**表单新增选项**：
```html
<div class="form-check mt-3">
    <input type="checkbox" class="form-check-input" id="useDescriptionAsSummary">
    <label class="form-check-label" for="useDescriptionAsSummary">使用description作为备选摘要</label>
    <small class="form-text text-muted d-block">勾选后，当RSS条目的summary质量不佳时，将使用description字段作为备选摘要</small>
</div>
```

**表格显示**：
- 在新闻源列表的"配置"列中显示备选摘要状态
- 对RSS源显示"使用备选摘要"或"仅summary"

**JavaScript处理**：
- 添加、编辑、保存新闻源时都处理新字段
- 向后兼容，默认值为false

## 使用场景

### 适用情况
1. **RSS源summary质量不佳**：内容过短、与标题重复
2. **description字段内容丰富**：包含更详细的文章描述
3. **需要更好的摘要质量**：提升用户阅读体验

### 不适用情况
1. **RSS源summary质量良好**：已有高质量摘要时不会使用description
2. **description字段缺失或质量差**：没有description或description质量不佳时会回退到其他方案

## 配置方法

1. **新建新闻源时**：
   - 在RSS配置区域勾选"使用description作为备选摘要"
   - 默认情况下此选项未勾选

2. **编辑现有新闻源**：
   - 点击编辑按钮打开新闻源配置
   - 在RSS配置区域调整备选摘要选项
   - 保存后立即生效

3. **查看当前设置**：
   - 在新闻源列表的"配置"列可以看到是否启用了备选摘要
   - RSS源会显示"使用备选摘要"或"仅summary"

## 技术细节

### 数据库迁移
```sql
ALTER TABLE sources ADD COLUMN use_description_as_summary BOOLEAN DEFAULT 0;
```

### 向后兼容性
- 现有新闻源默认禁用备选摘要功能
- API响应中使用`getattr(source, "use_description_as_summary", False)`确保兼容性
- 前端JavaScript中处理undefined值，提供默认值

### 性能影响
- 备选摘要检查仅在需要时执行，不会影响正常流程
- 对于Newspaper4k模式，仅在检测到需要时才创建feed_entry副本
- 不影响现有的HTML清理和其他处理流程

## 预期效果

### 摘要质量提升
- 减少"摘要不可用"的情况
- 提供更有意义的文章摘要
- 改善用户阅读体验

### 系统稳定性
- 保持向后兼容性，不影响现有功能
- 提供多层备选方案，确保总能获得某种形式的摘要
- 错误处理机制完善，失败时有合理的回退策略

### 灵活性
- 每个新闻源可以独立配置是否启用备选摘要
- 管理员可以根据具体RSS源的特点调整设置
- 支持运行时动态修改配置

## 维护说明

- 如需调整摘要质量判断标准，修改`get_rss_entry_article_data`函数中的条件
- 如需修改description质量检查标准，调整相应的长度和内容检查逻辑
- 前端显示内容可在admin.html中的相应位置修改 