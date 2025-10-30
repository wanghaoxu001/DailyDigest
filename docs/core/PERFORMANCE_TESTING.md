# 前端性能测试指南

## 测试目的

验证前端优化的效果，确保页面加载速度、交互响应和用户体验达到预期标准。

## 测试工具

### 1. Chrome DevTools
- **Network面板**: 检查资源加载时间和大小
- **Performance面板**: 分析运行时性能
- **Lighthouse**: 综合性能评分

### 2. 在线工具
- **WebPageTest**: https://www.webpagetest.org/
- **GTmetrix**: https://gtmetrix.com/
- **PageSpeed Insights**: https://pagespeed.web.dev/

## 测试场景

### 场景1: 首页加载性能

#### 测试步骤
1. 清除浏览器缓存
2. 打开 Chrome DevTools Network 面板
3. 访问 `http://localhost:8000/`
4. 记录以下指标：
   - **FCP (First Contentful Paint)**: 首次内容绘制
   - **LCP (Largest Contentful Paint)**: 最大内容绘制
   - **TTI (Time to Interactive)**: 可交互时间
   - **TBT (Total Blocking Time)**: 总阻塞时间

#### 预期结果
- FCP < 1.5s
- LCP < 2.5s
- TTI < 3.5s
- TBT < 300ms

### 场景2: 新闻页面加载

#### 测试步骤
1. 访问 `http://localhost:8000/news`
2. 观察加载过程：
   - CSS 和 JS 文件是否从缓存加载
   - 是否显示骨架屏或加载状态
   - 数据加载是否平滑

#### 预期结果
- 首次访问: LCP < 3.0s
- 重复访问: LCP < 1.5s (利用缓存)
- 显示加载状态，无白屏

### 场景3: 滚动性能

#### 测试步骤
1. 访问新闻页面并加载至少20条新闻
2. 打开 Chrome DevTools Performance 面板
3. 开始录制
4. 快速滚动页面
5. 停止录制并分析

#### 预期结果
- 帧率稳定在 55-60 FPS
- 无明显的掉帧或卡顿
- Scripting 时间 < 50ms/frame

### 场景4: 筛选操作性能

#### 测试步骤
1. 在新闻页面快速切换多个筛选条件
2. 观察响应时间和页面更新

#### 预期结果
- 防抖生效，避免频繁请求
- 用户输入后 300ms 内发起请求
- UI更新流畅，无阻塞

### 场景5: 移动端体验

#### 测试步骤
1. 使用 Chrome DevTools 设备模拟
2. 测试以下设备：
   - iPhone 12 Pro (390×844)
   - iPad Air (820×1180)
   - Samsung Galaxy S21 (360×800)
3. 验证：
   - 触摸目标大小 ≥ 44px
   - 文本可读性
   - 布局适配

#### 预期结果
- 所有按钮可轻松点击
- 文字大小合适，无需放大
- 布局不错位或溢出

## 性能基准

### 优化前基准
| 指标 | 首页 | 新闻页 |
|------|------|--------|
| 文件大小 | ~200KB | ~300KB |
| FCP | 2.1s | 2.8s |
| LCP | 3.2s | 4.5s |
| TTI | 4.0s | 5.2s |

### 优化后目标
| 指标 | 首页 | 新闻页 |
|------|------|--------|
| 文件大小 | ~150KB | ~200KB |
| FCP | < 1.5s | < 2.0s |
| LCP | < 2.5s | < 3.0s |
| TTI | < 3.0s | < 4.0s |

## Lighthouse评分目标

- **Performance**: ≥ 90
- **Accessibility**: ≥ 90
- **Best Practices**: ≥ 90
- **SEO**: ≥ 80

## 手动测试检查清单

### 功能测试
- [ ] 所有页面正常加载
- [ ] 导航菜单工作正常
- [ ] 筛选功能正常
- [ ] 新闻选择和快报生成功能正常
- [ ] 模态框正常打开和关闭

### 性能测试
- [ ] 页面加载速度符合预期
- [ ] 滚动流畅无卡顿
- [ ] 动画过渡自然
- [ ] 无内存泄漏
- [ ] 资源正确缓存

### 响应式测试
- [ ] 手机端布局正常
- [ ] 平板端布局正常
- [ ] 桌面端布局正常
- [ ] 触摸操作友好
- [ ] 横屏/竖屏切换正常

### 可访问性测试
- [ ] 键盘可以导航所有交互元素
- [ ] 焦点样式清晰可见
- [ ] 图片有alt属性
- [ ] ARIA标签正确
- [ ] 颜色对比度足够

### 浏览器兼容性
- [ ] Chrome 最新版
- [ ] Firefox 最新版
- [ ] Safari 最新版
- [ ] Edge 最新版
- [ ] 移动端浏览器

## 性能监控

### Chrome DevTools 使用

#### 1. Network面板分析
```
1. 打开 DevTools (F12)
2. 切换到 Network 面板
3. 勾选 "Disable cache"
4. 刷新页面
5. 查看：
   - 总请求数
   - 总传输大小
   - 总加载时间
   - 瀑布图
```

#### 2. Performance面板分析
```
1. 打开 DevTools Performance 面板
2. 点击录制按钮
3. 执行操作（滚动、点击等）
4. 停止录制
5. 分析：
   - FPS图表
   - 主线程活动
   - 网络活动
   - 帧渲染时间
```

#### 3. Lighthouse报告
```
1. 打开 DevTools Lighthouse 面板
2. 选择测试类别：
   - Performance
   - Accessibility
   - Best Practices
   - SEO
3. 选择设备类型（Mobile/Desktop）
4. 点击 "Generate report"
5. 查看评分和建议
```

### 性能指标说明

#### Core Web Vitals
- **LCP (Largest Contentful Paint)**: 
  - Good: < 2.5s
  - Needs Improvement: 2.5s - 4.0s
  - Poor: > 4.0s

- **FID (First Input Delay)**: 
  - Good: < 100ms
  - Needs Improvement: 100ms - 300ms
  - Poor: > 300ms

- **CLS (Cumulative Layout Shift)**: 
  - Good: < 0.1
  - Needs Improvement: 0.1 - 0.25
  - Poor: > 0.25

## 问题排查

### 常见性能问题

#### 1. 加载慢
**可能原因**:
- CDN响应慢
- 资源未压缩
- 未启用缓存

**解决方案**:
- 检查网络连接
- 启用gzip/brotli压缩
- 配置缓存头

#### 2. 滚动卡顿
**可能原因**:
- 过多的重排重绘
- JavaScript执行时间过长
- 复杂的CSS选择器

**解决方案**:
- 使用 transform 代替 position
- 优化JavaScript性能
- 简化CSS选择器

#### 3. 内存泄漏
**可能原因**:
- 事件监听器未清理
- 定时器未清除
- DOM引用未释放

**解决方案**:
- 移除不用的事件监听器
- 清除定时器
- 释放DOM引用

## 持续监控

### 建议的监控策略

1. **定期测试**: 每周运行一次 Lighthouse
2. **关键指标**: 监控 LCP、FID、CLS
3. **真实用户监控**: 考虑集成 RUM 工具
4. **性能预算**: 设置并维护性能预算

### 性能预算示例

```
{
  "budget": [
    {
      "resourceType": "document",
      "budget": 50  // KB
    },
    {
      "resourceType": "script",
      "budget": 150  // KB
    },
    {
      "resourceType": "stylesheet",
      "budget": 50  // KB
    },
    {
      "resourceType": "total",
      "budget": 300  // KB
    }
  ]
}
```

## 测试报告模板

### 性能测试报告

**测试日期**: YYYY-MM-DD
**测试人员**: 
**测试环境**: 
- 操作系统: 
- 浏览器: 
- 网络: 

**测试结果**:

| 页面 | FCP | LCP | TTI | Lighthouse分数 |
|------|-----|-----|-----|----------------|
| 首页 |     |     |     |                |
| 新闻 |     |     |     |                |

**发现的问题**:
1. 
2. 
3. 

**建议**:
1. 
2. 
3. 

**结论**:


## 参考资料

- [Web Vitals](https://web.dev/vitals/)
- [Chrome DevTools Performance](https://developer.chrome.com/docs/devtools/performance/)
- [Lighthouse Scoring Guide](https://web.dev/performance-scoring/)
- [WebPageTest Documentation](https://docs.webpagetest.org/)

