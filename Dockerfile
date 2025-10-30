FROM python:3.11

# 构建参数，用于区分开发和生产环境
ARG BUILD_ENV=production

# 设置工作目录
WORKDIR /app

# 设置时区为北京时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 更新包列表并安装系统依赖和调试工具
RUN apt-get update && apt-get install -y \
    # 时区数据包
    tzdata \
    # Cron 定时任务服务
    cron \
    # Playwright 浏览器依赖
    wget \
    jq \
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
    fonts-noto-cjk \
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

# 根据构建环境决定是否复制代码
# 开发环境不复制代码，使用挂载；生产环境复制代码到镜像
RUN if [ "$BUILD_ENV" = "development" ]; then \
        echo "Building for development - code will be mounted at runtime"; \
    else \
        echo "Building for production - copying code into image"; \
    fi

# 生产环境：复制所有应用代码
RUN if [ "$BUILD_ENV" = "production" ]; then \
        echo "Will copy code in next step"; \
    fi

# 只有生产环境才复制代码，开发环境通过挂载获取
COPY . /tmp/app_code
RUN if [ "$BUILD_ENV" = "production" ]; then \
        cp -r /tmp/app_code/* /app/ && \
        rm -rf /tmp/app_code; \
    else \
        rm -rf /tmp/app_code; \
    fi

# 创建必要的目录
RUN mkdir -p /app/data/logs /app/data/outputs /app/data/wechat_articles /app/data/processed_articles /app/logs

# 设置环境变量
ENV PYTHONPATH=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
ENV PROJECT_ROOT=/app

# 复制entrypoint脚本
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 暴露端口
EXPOSE 18899

# 使用entrypoint脚本启动
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "run.py"]