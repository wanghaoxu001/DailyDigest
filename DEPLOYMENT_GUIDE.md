# 每日安全快报系统 - 部署指南

[![部署状态](https://img.shields.io/badge/deployment-ready-green.svg)](./DEPLOYMENT_GUIDE.md)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-supported-blue.svg)](https://www.docker.com/)

## 📋 目录

- [系统要求](#系统要求)
- [本地部署](#本地部署)
- [Docker 容器部署](#docker-容器部署)
- [环境配置](#环境配置)
- [数据库初始化](#数据库初始化)
- [服务验证](#服务验证)
- [生产环境配置](#生产环境配置)
- [常见问题排查](#常见问题排查)

## 🖥️ 系统要求

### 最低配置
- **操作系统**: Linux (Ubuntu 18.04+) / macOS 10.15+ / Windows 10+
- **Python**: 3.8 或更高版本
- **内存**: 2GB RAM (推荐 4GB+)
- **存储**: 5GB 可用空间
- **网络**: 需要访问 OpenAI API 和外部新闻源

### 推荐配置 (生产环境)
- **CPU**: 2核以上
- **内存**: 8GB RAM
- **存储**: 20GB SSD
- **网络**: 稳定的互联网连接

## 🏠 本地部署

### 1. 环境准备

#### Ubuntu/Debian 系统
```bash
# 更新系统包
sudo apt-get update && sudo apt-get upgrade -y

# 安装 Python 和基础工具
sudo apt-get install -y python3 python3-pip python3-venv git curl

# 安装系统依赖 (Playwright 需要)
sudo apt-get install -y \
    wget gnupg ca-certificates fonts-liberation \
    libasound2 libatk-bridge2.0-0 libdrm2 libgtk-3-0 \
    libnspr4 libnss3 libx11-xcb1 libxcomposite1 \
    libxdamage1 libxrandr2 xvfb \
    fonts-wqy-zenhei fonts-wqy-microhei
```

### 2. 获取项目代码

```bash
# 克隆项目仓库或进入项目目录
cd DailyDigest
```

### 3. 创建虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 升级 pip
pip install --upgrade pip
```

### 4. 安装依赖

```bash
# 安装项目依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
python -m playwright install chromium

# 下载 NLTK 数据
python -c "
import nltk
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')
print('NLTK 数据下载完成')
"
```

### 5. 环境配置

```bash
# 复制环境配置模板
cp envtemplate.txt .env

# 编辑配置文件
nano .env
```

在 `.env` 文件中配置：

```bash
# OpenAI API 配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# 数据库配置
DATABASE_URL=sqlite:///daily_digest.db

# 服务器配置
HOST=0.0.0.0
PORT=18899
DEBUG=False

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=data/logs/daily_digest.log
```

### 6. 数据库初始化

```bash
# 初始化数据库
python -c "
from app.db.session import engine
from app.db.base import Base
from app.models import *
Base.metadata.create_all(bind=engine)
print('数据库初始化完成')
"
```

### 7. 启动服务

```bash
# 启动应用
python run.py

# 或使用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 18899

# 后台运行
nohup python run.py > app.log 2>&1 &
```

## 🐳 Docker 容器部署

### 1. 快速启动

```bash
# 确保已安装 Docker 和 Docker Compose
docker --version
docker-compose --version

# 复制环境配置
cp envtemplate.txt .env
# 编辑 .env 文件，添加 OpenAI API Key

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f daily-digest
```

### 2. 构建和管理

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps
```

### 3. 数据持久化

Docker 配置自动处理数据持久化：

- **数据库**: `./daily_digest.db` 映射到容器内
- **数据文件**: `./data` 目录映射到容器内
- **环境配置**: `./.env` 文件映射到容器内

## ⚙️ 环境配置

### 环境变量说明

| 变量名 | 说明 | 默认值 | 必填 |
|--------|------|--------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | - | ✅ |
| `OPENAI_BASE_URL` | OpenAI API 基础URL | https://api.openai.com/v1 | ❌ |
| `OPENAI_MODEL` | 使用的模型 | gpt-3.5-turbo | ❌ |
| `DATABASE_URL` | 数据库连接URL | sqlite:///daily_digest.db | ❌ |
| `HOST` | 服务监听地址 | 0.0.0.0 | ❌ |
| `PORT` | 服务端口 | 18899 | ❌ |
| `DEBUG` | 调试模式 | False | ❌ |
| `LOG_LEVEL` | 日志级别 | INFO | ❌ |

## ✅ 服务验证

### 1. 基础功能测试

```bash
# 测试服务启动
curl http://localhost:18899/health

# 测试前端页面
curl http://localhost:18899/

# 测试 API 端点
curl http://localhost:18899/api/sources
```

### 2. 模块导入测试

```bash
python -c "
from app.crawlers.wechat.playwright_wechat_crawler import WechatArticleCrawler
from app.crawlers.parsers.security_digest_parser import SecurityDigestParser
print('✅ 所有核心模块导入成功')
"
```

## 🚀 生产环境配置

### 1. 反向代理配置 (Nginx)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:18899;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # 静态文件缓存
    location /static/ {
        alias /app/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2. 系统服务配置 (systemd)

创建 `/etc/systemd/system/daily-digest.service`：

```ini
[Unit]
Description=Daily Digest Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/DailyDigest
Environment=PATH=/opt/DailyDigest/venv/bin
ExecStart=/opt/DailyDigest/venv/bin/python run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable daily-digest
sudo systemctl start daily-digest
sudo systemctl status daily-digest
```

## 🐛 常见问题排查

### 1. Playwright 相关问题

**问题**: `playwright._impl._api_types.Error: Executable doesn't exist`

**解决方案**:
```bash
# 重新安装 Playwright 浏览器
python -m playwright install chromium

# 检查安装状态
python -c "from playwright.sync_api import sync_playwright; print('Playwright 正常')"
```

### 2. 内存相关问题

**问题**: 内存不足导致服务异常

**解决方案**:
```bash
# 添加 swap 空间
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 3. 网络相关问题

**问题**: OpenAI API 访问失败

**解决方案**:
```bash
# 测试网络连接
curl -I https://api.openai.com

# 检查环境变量
echo $OPENAI_API_KEY
```

### 4. 权限相关问题

**问题**: 文件写入权限不足

**解决方案**:
```bash
# 设置正确的文件权限
sudo chown -R www-data:www-data /opt/DailyDigest
sudo chmod -R 755 /opt/DailyDigest
sudo chmod -R 777 /opt/DailyDigest/data
```

### 5. 日志查看

```bash
# 查看应用日志
tail -f data/logs/daily_digest.log

# 查看系统服务日志
sudo journalctl -u daily-digest -f

# Docker 日志
docker-compose logs -f daily-digest
```

## 📊 监控和日志

### 1. 健康检查端点

应用提供以下监控端点：

- `GET /health` - 基础健康检查，返回系统状态

### 2. 日志结构

```
data/logs/
├── daily_digest.log     # 应用主日志
├── errors.log          # 错误日志
├── crawler.log         # 爬虫日志
└── llm_processor.log   # AI处理日志
```

### 3. 监控脚本示例

```bash
#!/bin/bash
# monitor.sh - 监控脚本

# 检查服务状态
if ! curl -f http://localhost:18899/health >/dev/null 2>&1; then
    echo "服务异常，正在重启..."
    systemctl restart daily-digest
fi
```

---

## 📞 技术支持

如果在部署过程中遇到问题，请：

1. 查看 [常见问题排查](#常见问题排查) 部分
2. 检查应用日志文件
3. 提交 Issue 并附上详细的错误信息

**部署成功后，访问 `http://your-server:18899` 即可使用系统！** 🎉
