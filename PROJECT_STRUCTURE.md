# 项目结构说明

## 📁 目录结构

```
DailyDigest/
├── app/                           # 核心应用代码
│   ├── api/                       # API端点
│   │   └── endpoints/             # 具体的API实现
│   ├── config/                    # 配置模块
│   ├── crawlers/                  # 爬虫模块 ⭐
│   │   ├── base/                  # 基础爬虫类
│   │   ├── wechat/                # 微信公众号爬虫
│   │   │   ├── playwright_wechat_crawler.py
│   │   │   └── wechat_article_processor.py
│   │   └── parsers/               # 文章解析器
│   │       ├── security_digest_parser.py
│   │       └── __init__.py
│   ├── db/                        # 数据库相关
│   │   └── migrations/            # 数据库迁移脚本
│   ├── models/                    # 数据模型
│   ├── services/                  # 业务逻辑服务
│   ├── static/                    # 静态资源
│   │   ├── css/
│   │   ├── fonts/
│   │   ├── js/
│   │   └── pdf/
│   └── templates/                 # Jinja2模板
├── data/                          # 数据文件 ⭐
│   ├── outputs/                   # 生成的快报输出
│   ├── logs/                      # 日志文件
│   ├── wechat_articles/           # 爬取的微信文章
│   ├── processed_articles/        # 处理后的文章
│   ├── parsed_news/               # 解析后的新闻
│   └── *.md, *.pdf               # 各种快报文件
├── docs/                          # 项目文档 ⭐
│   ├── README.md                  # 主要文档
│   ├── SCHEDULER_README.md        # 调度器文档
│   ├── PLAYWRIGHT_PDF_UPDATE.md   # PDF生成功能文档
│   └── *.md                      # 其他功能文档
├── scripts/                       # 脚本目录 ⭐
│   ├── database/                  # 数据库相关脚本
│   ├── debug/                     # 调试工具脚本
│   └── maintenance/               # 维护工具脚本
├── tests/                         # 测试代码 ⭐
├── tools/                         # 工具脚本 ⭐
│   └── clear_news.py             # 清理新闻数据工具
├── typora_md_github_theme/        # Typora主题
├── run.py                         # 应用启动入口
├── requirements.txt               # Python依赖
├── .env                          # 环境配置（需创建）
└── daily_digest.db               # SQLite数据库
```

## 🔄 重构变化

### ✅ 新增目录
- `app/crawlers/` - 爬虫相关代码模块化
- `data/` - 统一数据文件存储
- `docs/` - 集中项目文档
- `scripts/` - 脚本工具分类
- `tests/` - 测试代码专用目录

### 📦 模块化改进
- **爬虫模块** (`app/crawlers/`):
  - `wechat/` - 微信公众号相关爬虫
  - `parsers/` - 文章解析器
  - `base/` - 基础爬虫类（预留扩展）

### 🔗 引用更新
原来的文件引用已更新为新的模块路径：

```python
# 之前
from playwright_wechat_crawler import WechatArticleCrawler
from parsers.security_digest_parser import SecurityDigestParser

# 现在
from app.crawlers.wechat.playwright_wechat_crawler import WechatArticleCrawler
from app.crawlers.parsers.security_digest_parser import SecurityDigestParser
```

## 📋 使用指南

### 启动应用
```bash
python run.py
```

### 导入爬虫模块
```python
# 方式1：直接导入
from app.crawlers.wechat.playwright_wechat_crawler import WechatArticleCrawler

# 方式2：从主模块导入
from app.crawlers import WechatArticleCrawler, SecurityDigestParser
```

### 项目扩展
- 添加新爬虫：在 `app/crawlers/` 下创建对应目录
- 添加新解析器：在 `app/crawlers/parsers/` 下添加文件
- 添加工具脚本：在 `scripts/` 相应子目录下添加
- 添加测试：在 `tests/` 目录下添加测试文件

## 🎯 优势

1. **模块化清晰**：不同功能分模块组织
2. **扩展性好**：新功能容易添加和维护
3. **文档集中**：所有文档统一管理
4. **数据分类**：输入输出数据分类存储
5. **工具分类**：脚本和工具按功能分类 