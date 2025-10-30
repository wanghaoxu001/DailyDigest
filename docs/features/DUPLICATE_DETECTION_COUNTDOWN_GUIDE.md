# 重复新闻检测倒计时功能使用指南

## 功能概述

本功能为快报的重复新闻检测过程添加了预估倒计时，让用户了解检测进度和预计完成时间。

### 主要特性

1. **时间预估算法**：基于历史LLM调用时间和新闻数量计算预估时间
2. **实时倒计时**：显示检测进度和剩余时间
3. **进度追踪**：实时更新检测进度条和状态
4. **自适应调整**：根据实际进度动态调整倒计时
5. **模拟数据支持**：支持模拟不同规模的测试场景

## 核心文件

### 后端文件
- `app/services/duplicate_detection_timer.py` - 时间预估和倒计时服务
- `app/services/duplicate_detector.py` - 重复检测服务（已集成时间跟踪）
- `app/models/digest.py` - 快报模型（添加了开始时间字段）
- `app/api/endpoints/digest.py` - API接口（添加了预估和进度接口）
- `app/db/migrations/add_detection_started_at.py` - 数据库迁移脚本

### 前端文件
- `app/templates/digest.html` - 快报页面（添加了倒计时显示）

### 测试工具
- `test_duplicate_detection_timing.py` - 性能测试工具

## API 接口

### 1. 获取时间预估
```
GET /api/digest/{digest_id}/duplicate-detection-estimate
```

返回示例：
```json
{
  "digest_id": 123,
  "estimation": {
    "total_comparisons": 150,
    "estimated_duration_seconds": 450.0,
    "estimated_duration_minutes": 7.5,
    "avg_llm_call_time": 2.8,
    "current_news_count": 10,
    "reference_news_count": 15,
    "buffer_factor": 1.3,
    "estimated_completion_time": "2025-01-15T10:15:30.000Z"
  }
}
```

### 2. 获取检测进度
```
GET /api/digest/{digest_id}/duplicate-detection-progress
```

返回示例：
```json
{
  "digest_id": 123,
  "detection_status": "running",
  "started_at": "2025-01-15T10:08:00.000Z",
  "progress": {
    "completed_comparisons": 45,
    "total_comparisons": 150,
    "current_progress": 30.0,
    "elapsed_time_seconds": 126.5,
    "elapsed_time_minutes": 2.1,
    "estimated_remaining_time_seconds": 315.2,
    "estimated_remaining_time_minutes": 5.3,
    "estimated_completion_time": "2025-01-15T10:13:15.200Z"
  }
}
```

### 3. 模拟测试数据
```
POST /api/digest/{digest_id}/duplicate-detection-simulation?current_news_count=10&reference_news_count=30
```

## 前端功能

### 显示组件

1. **预估信息面板**：显示在快报内容顶部
   - 总比较次数
   - 预估总时间
   - 预计完成时间
   - 实时倒计时
   - 进度条

2. **状态指示器**：
   - 蓝色：正在检测（超过2分钟剩余）
   - 橙色：接近完成（1-2分钟剩余）
   - 绿色：即将完成（少于30秒）

3. **进度条**：
   - 条纹动画表示检测进行中
   - 实时更新百分比和完成数量

### 用户体验

- **自动启动**：查看快报时自动获取预估并开始倒计时
- **实时更新**：每10秒更新一次检测状态和进度
- **完成提示**：检测完成时自动移除倒计时显示
- **错误处理**：预估失败时显示简化的检测状态

## 测试工具使用

### 1. 基本模拟测试
```bash
python test_duplicate_detection_timing.py --simulate-only
```

### 2. 综合测试
```bash
python test_duplicate_detection_timing.py --comprehensive
```

### 3. 基准测试
```bash
python test_duplicate_detection_timing.py --benchmark --max-news 20
```

### 测试结果示例

#### 综合测试结果
```
=== 测试结果总结 ===
成功测试场景: 5/5
比较次数范围: 75 - 1200
预估时间范围: 3.2 - 51.4 分钟
平均每次比较耗时: 2.57秒
```

#### 基准测试结果
```
新闻数量 | 比较次数 | 预估时间(分钟)
----------------------------------------
       5 |      150 |          6.4
      10 |      300 |         12.8
      15 |      450 |         19.3
      20 |      600 |         25.7
```

## 配置参数

### 环境变量
- `OPENAI_DUPLICATE_DETECTOR_MODEL`: 重复检测使用的模型（默认：ark-deepseek-r1-250528）

### 时间预估参数（可在 `duplicate_detection_timer.py` 中调整）
- `default_llm_call_time`: 默认LLM调用时间（3.0秒）
- `buffer_factor`: 缓冲因子（1.3，增加30%时间）
- `network_delay`: 网络延迟（0.5秒）
- `max_records`: 最大时间记录数（100条）

## 部署和使用

### 1. 数据库迁移
```bash
python -m app.db.update_schema
```

### 2. 重启应用
```bash
./scripts/quick-restart.sh
```

### 3. 验证功能
1. 创建一个新的快报
2. 查看快报详情
3. 检查是否显示预估时间和倒计时
4. 等待检测完成并验证倒计时准确性

## 性能优化建议

### 1. LLM调用优化
- 使用更快的模型进行重复检测
- 实施请求批处理（如果模型支持）
- 添加本地缓存减少重复调用

### 2. 算法优化
- 实施智能停止（高相似度时提前停止）
- 使用更高效的相似度算法预筛选
- 并行处理多个新闻比较

### 3. 用户体验优化
- 添加"跳过检测"选项
- 支持后台检测，用户可以继续其他操作
- 提供检测历史和统计信息

## 故障排除

### 常见问题

1. **倒计时不显示**
   - 检查快报是否正在进行重复检测
   - 确认API接口 `/duplicate-detection-estimate` 正常工作
   - 查看浏览器控制台是否有JavaScript错误

2. **时间预估不准确**
   - 运行模拟测试生成更多历史数据
   - 调整缓冲因子参数
   - 检查网络延迟设置

3. **进度更新缓慢**
   - 检查数据库连接
   - 确认LLM API调用正常
   - 查看后端日志了解检测状态

### 调试命令
```bash
# 查看检测状态
curl http://localhost:18899/api/digest/123/duplicate-detection-status

# 查看时间预估
curl http://localhost:18899/api/digest/123/duplicate-detection-estimate

# 查看检测进度
curl http://localhost:18899/api/digest/123/duplicate-detection-progress
```

## 未来改进方向

1. **机器学习优化**：基于历史数据训练更准确的时间预估模型
2. **用户个性化**：根据用户习惯调整显示偏好
3. **通知系统**：检测完成时发送邮件或推送通知
4. **批处理模式**：支持多个快报同时进行重复检测
5. **移动端优化**：针对手机用户优化倒计时显示

---

> **注意**：此功能需要有效的OpenAI API密钥和至少一些历史快报数据才能正常工作。首次使用时建议运行模拟测试以生成基础时间数据。