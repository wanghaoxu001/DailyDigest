# 时区配置说明

本项目已完全配置为使用北京时间（Asia/Shanghai），确保在Docker容器中运行时时间显示正确。

## 📋 配置概述

### 镜像层面时区固化
在 `Dockerfile` 和 `Dockerfile.dev` 中已添加以下配置：

```dockerfile
# 设置时区为北京时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装时区数据包
RUN apt-get update && apt-get install -y \
    tzdata \
    # ... 其他依赖
```

### 容器层面时区配置
在 `docker compose.yml` 和 `docker compose.dev.yml` 中配置：

```yaml
services:
  daily-digest:
    volumes:
      # 时区文件挂载（双重保证）
      - /etc/localtime:/etc/localtime:ro
      - /etc/timezone:/etc/timezone:ro
    environment:
      - TZ=Asia/Shanghai
```

## 🛠️ 部署和验证

### 1. 构建镜像
```bash
# 生产环境
docker compose build

# 开发环境
docker compose -f docker compose.dev.yml build
```

### 2. 启动服务
```bash
# 生产环境
docker compose up -d

# 开发环境
docker compose -f docker compose.dev.yml up -d
```

### 3. 验证时区设置
```bash
# 运行时区测试脚本
docker compose exec daily-digest python scripts/test_timezone.py

# 或者手动检查
docker compose exec daily-digest date
docker compose exec daily-digest cat /etc/timezone
```

## 🕐 时区配置的优势

### 1. 多层保护
- **镜像层面**: Dockerfile中固化时区，无论在何处运行都是北京时间
- **容器层面**: docker compose中配置环境变量和挂载，双重保证
- **应用层面**: Python应用自动使用系统时区

### 2. 数据一致性
- **新闻抓取**: RSS时间解析后保存为北京时间
- **日志记录**: 所有日志时间戳都是北京时间  
- **快报生成**: 快报中的时间显示为北京时间
- **API响应**: 前端显示的时间都是北京时间

### 3. 兼容性
- **本地开发**: 无论宿主机什么时区，容器内都是北京时间
- **服务器部署**: 不依赖服务器时区设置
- **跨环境**: 开发、测试、生产环境时区统一

## 📊 时间字段说明

在项目中有三个重要的时间字段：

```python
class News(Base):
    publish_date = Column(DateTime, nullable=True)     # 文章发布时间（来自RSS）
    fetched_at = Column(DateTime, default=func.now()) # 抓取时间（北京时间）
    created_at = Column(DateTime, default=func.now()) # 创建时间（北京时间）
```

- `publish_date`: 来自RSS源的原始发布时间，转换为北京时间
- `fetched_at`: 文章被系统抓取的时间（北京时间）
- `created_at`: 数据库记录创建时间（北京时间）

## 🔧 故障排除

### 1. 时区显示不正确
```bash
# 检查容器内时区
docker compose exec daily-digest date
# 应该显示：Fri Jun 14 10:30:00 CST 2024

# 检查环境变量
docker compose exec daily-digest env | grep TZ
# 应该显示：TZ=Asia/Shanghai
```

### 2. 时区文件不存在
```bash
# 检查时区文件
docker compose exec daily-digest ls -la /etc/timezone
docker compose exec daily-digest ls -la /etc/localtime

# 重新构建镜像
docker compose build --no-cache
```

### 3. Python时间不正确
```bash
# 运行测试脚本
docker compose exec daily-digest python scripts/test_timezone.py

# 检查Python时区
docker compose exec daily-digest python -c "
from datetime import datetime
import pytz
print('本地时间:', datetime.now())
print('北京时间:', datetime.now(pytz.timezone('Asia/Shanghai')))
"
```

## 📝 注意事项

1. **重新构建**: 修改Dockerfile后需要重新构建镜像
2. **数据迁移**: 如果已有数据，时区变更不会影响历史数据
3. **API接口**: 所有时间相关的API响应都使用北京时间
4. **日志文件**: 日志中的时间戳都是北京时间

## 🔄 升级指南

如果从旧版本升级，请执行以下步骤：

```bash
# 1. 停止服务
docker compose down

# 2. 重新构建镜像
docker compose build --no-cache

# 3. 启动服务
docker compose up -d

# 4. 验证时区
docker compose exec daily-digest python scripts/test_timezone.py
```

完成后，系统将完全使用北京时间运行。
