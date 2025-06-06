# max_fetch_days 功能实现总结

## 📋 功能概述

为每日安全快报系统新增了 **max_fetch_days** 配置功能，允许用户在前端界面配置订阅源拉取新闻时最多拉取最近X天的文章，有效防止拉取时间过久，提升系统性能。

## ✨ 实现的功能

### 1. 数据库层面
- ✅ `Source` 模型已包含 `max_fetch_days` 字段，默认值为7天
- ✅ 支持1-30天的配置范围
- ✅ 数据库迁移脚本已实现，自动为现有数据设置默认值

### 2. API 层面
- ✅ **创建新闻源**: 支持设置 `max_fetch_days` 参数
- ✅ **更新新闻源**: 支持修改 `max_fetch_days` 配置
- ✅ **获取新闻源**: 响应中包含 `max_fetch_days` 字段
- ✅ API 验证和错误处理完善

### 3. 前端界面
- ✅ 新闻源管理页面新增"最多拉取天数"配置字段
- ✅ 表单验证：限制输入范围1-30天
- ✅ 新闻源列表显示配置信息
- ✅ 添加/编辑新闻源时支持设置和修改该值
- ✅ 用户友好的提示信息

### 4. 爬虫逻辑
- ✅ RSS 抓取时根据 `max_fetch_days` 计算截止日期
- ✅ 自动跳过发布时间超出限制的文章
- ✅ 详细的日志记录，便于调试和监控
- ✅ 多种日期格式的兼容处理

## 🔧 技术实现细节

### 数据模型更新
```python
# app/models/source.py
max_fetch_days = Column(Integer, default=7)  # 最多拉取最近X天的文章，默认7天
```

### API 更新
```python
# app/api/endpoints/sources.py
class SourceBase(BaseModel):
    max_fetch_days: int = 7  # 最多拉取最近X天的文章，默认7天
```

### 前端界面更新
```html
<!-- 新增的表单字段 -->
<div class="mb-3">
    <label for="sourceMaxFetchDays" class="form-label">最多拉取天数</label>
    <input type="number" class="form-control" id="sourceMaxFetchDays" 
           value="7" min="1" max="30" required>
    <small class="form-text text-muted">
        设置订阅源拉取新闻时最多拉取最近X天的文章，防止拉取时间过久（1-30天）
    </small>
</div>
```

### 爬虫逻辑更新
```python
# app/services/crawler.py
# 获取时间限制，默认7天
max_fetch_days = getattr(source, 'max_fetch_days', 7)
cutoff_date = datetime.now() - timedelta(days=max_fetch_days)

# 检查文章发布时间是否在允许范围内
if article_date and article_date < cutoff_date:
    logger.info(f"RSS: 跳过过期文章 (发布于 {article_date}, 截止日期 {cutoff_date}): {article_data['title'][:30]}...")
    continue
```

## 🧪 测试验证

运行测试脚本 `test_max_fetch_days.py` 验证功能完整性：

```bash
python test_max_fetch_days.py
```

测试覆盖：
- ✅ API 创建、读取、更新、删除功能
- ✅ 前端界面元素存在性检查
- ✅ 数据一致性验证
- ✅ 错误处理测试

## 📊 使用效果

### 性能优化
- **减少抓取时间**: 避免处理过旧的文章
- **降低资源消耗**: 减少不必要的网络请求和数据处理
- **提升用户体验**: 更快的抓取速度和响应时间

### 灵活配置
- **个性化设置**: 不同新闻源可设置不同的时间限制
- **适应性强**: 支持1-30天的灵活范围
- **易于管理**: 前端界面直观操作

## 🔄 向后兼容

- ✅ 现有新闻源自动获得默认值（7天）
- ✅ 数据库结构平滑升级
- ✅ API 保持向后兼容
- ✅ 前端界面渐进增强

## 📝 使用说明

### 配置新闻源时间限制

1. 访问管理页面：`http://localhost:18899/admin`
2. 点击"添加新闻源"或编辑现有新闻源
3. 在"最多拉取天数"字段设置所需的天数（1-30天）
4. 保存配置

### 查看配置效果

1. 新闻源列表中会显示每个源的配置信息
2. 手动触发抓取时，日志会显示时间过滤信息
3. 系统会自动跳过超出时间限制的文章

## 🎯 预期效果

实施该功能后，系统将：
- **提升抓取效率**: 减少不必要的历史文章处理
- **节省资源**: 降低网络带宽和计算资源消耗
- **改善体验**: 更快速的新闻更新和处理
- **增强控制**: 用户可根据需求灵活配置时间范围

---

*该功能已完全实现并测试通过，可以立即投入使用。* 