FROM python:3.11

# 设置工作目录
WORKDIR /app

# 更新包列表并安装系统依赖和调试工具
RUN apt-get update && apt-get install -y \
    # Playwright 浏览器依赖
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xvfb \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    # 基础开发和调试工具
    git \
    curl \
    wget \
    vim \
    nano \
    htop \
    tree \
    less \
    coreutils \
    gawk \
    sed \
    # 网络调试工具
    net-tools \
    iputils-ping \
    telnet \
    netcat-openbsd \
    nmap \
    # 系统监控工具
    procps \
    psmisc \
    lsof \
    strace \
    # 文件处理工具
    zip \
    unzip \
    tar \
    gzip \
    # Python 调试工具
    python3-dev \
    python3-pip \
    # 其他有用工具
    jq \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器
RUN python -m playwright install
RUN python -m playwright install chromium
RUN python -m playwright install-deps

# 下载 NLTK 数据
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('averaged_perceptron_tagger')"

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p data/logs data/outputs data/wechat_articles data/processed_articles

# 设置环境变量
ENV PYTHONPATH=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# 暴露端口
EXPOSE 18899

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:18899/health || exit 1

# 启动命令
CMD ["python", "run.py"] 