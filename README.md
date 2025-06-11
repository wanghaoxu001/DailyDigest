# 每日安全快报系统 (Daily Security Digest System)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🚀 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置环境
```bash
cp envtemplate.txt .env
# 编辑 .env 文件，添加你的 OpenAI API Key 等配置
```

### 启动应用
```bash
python run.py
```

访问 `http://localhost:18899` 查看Web界面。

## 📖 文档

详细文档请查看：
- [项目结构说明](PROJECT_STRUCTURE.md) - 了解项目架构和组织
- [完整文档](docs/README.md) - 详细使用指南
- [调度器文档](docs/SCHEDULER_README.md) - 定时任务配置
- [PDF生成功能](docs/PLAYWRIGHT_PDF_UPDATE.md) - PDF导出功能

## 🏗️ 项目结构

```
DailyDigest/
├── app/                    # 核心应用代码
│   ├── crawlers/          # 爬虫模块 🆕
│   ├── api/               # API端点
│   ├── services/          # 业务服务
│   └── models/            # 数据模型
├── data/                  # 数据文件 🆕
├── docs/                  # 项目文档 🆕
├── scripts/               # 脚本工具 🆕
├── tests/                 # 测试代码 🆕
└── tools/                 # 工具脚本 🆕
```

## ✨ 主要功能

- 🌐 **多源新闻采集** - 支持RSS、网页和微信公众号
- 🤖 **AI智能处理** - 使用OpenAI API进行内容分析和分类
- 🔄 **智能去重** - 基于语义和实体的重复内容检测
- 📊 **分类管理** - 金融、重大事件、数据泄露、漏洞风险等分类
- 📄 **多格式导出** - 支持Markdown和PDF格式
- ⏰ **定时任务** - 自动化新闻采集和处理
- 🎨 **现代化UI** - 基于Bootstrap的响应式界面

## 🛠️ 技术栈

- **后端**: FastAPI + SQLAlchemy + SQLite
- **前端**: Jinja2 + Bootstrap + JavaScript
- **爬虫**: Playwright + Newspaper3k + BeautifulSoup
- **AI处理**: OpenAI GPT API
- **PDF生成**: Playwright PDF
- **任务调度**: APScheduler

## 📝 许可证

[MIT License](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

更多详细信息请查看 [docs/](docs/) 目录下的文档。 