# Docker 统一配置使用说明

现在 DailyDigest 使用统一的 Docker 配置文件，支持开发和生产环境，代码和数据库都采用挂载方式。

## 快速开始

### 1. 环境配置
```bash
# 复制环境配置文件
cp env.example .env

# 根据需要修改 .env 文件中的配置
vim .env
```

### 2. 生产环境启动
```bash
# 默认启动生产环境
docker compose up -d

# 或者显式指定生产环境
BUILD_ENV=production docker compose up -d
```

### 3. 开发环境启动
```bash
# 启动开发环境（代码挂载，修改立即生效）
docker compose --profile dev up

# 或者使用环境变量
BUILD_ENV=development docker compose --profile dev up
```

## 详细用法

### 环境区分

| 环境 | 配置文件 | 代码处理 | 重启策略 | 健康检查 |
|------|----------|----------|----------|----------|
| 生产环境 | `.env` 中 `BUILD_ENV=production` | 构建时复制到镜像 | unless-stopped | 启用 |
| 开发环境 | `.env` 中 `BUILD_ENV=development` | 挂载目录，实时更新 | no | 可选 |

### 服务启动方式

#### 只启动主服务（生产）
```bash
docker compose up -d daily-digest
```

#### 启动开发环境
```bash
# 启动开发服务
docker compose --profile dev up daily-digest-dev

# 带 Redis 的开发环境
docker compose --profile dev up
```

#### 启动完整环境（主服务 + Redis）
```bash
docker compose --profile full up -d
```

### 目录挂载说明

所有环境都会挂载以下目录：
- `./data` → `/app/data` （数据目录）
- `./daily_digest.db` → `/app/daily_digest.db` （数据库文件）
- `./.env` → `/app/.env` （环境配置）

开发环境额外挂载：
- `.` → `/app` （整个项目代码，排除缓存目录）

### 常用命令

```bash
# 构建镜像
docker compose build

# 查看日志
docker compose logs -f daily-digest

# 进入容器调试
docker compose exec daily-digest bash

# 停止服务
docker compose down

# 清理所有数据
docker compose down -v
```

### 端口配置

默认端口：18899

可通过 `.env` 文件修改：
```env
PORT=18899          # 生产环境端口
DEV_PORT=18899      # 开发环境端口
```

### 环境变量说明

主要环境变量（在 `.env` 中配置）：

- `BUILD_ENV`: 构建环境 (production/development)
- `FLASK_ENV`: Flask 环境 (production/development)  
- `PORT`: 服务端口
- `RESTART_POLICY`: 重启策略
- `COMPOSE_PROFILES`: Compose profiles

详细配置请查看 `env.example` 文件。

## 迁移指南

从多版本配置迁移到统一配置：

1. 备份当前配置（可选）
2. 使用新的统一配置文件
3. 根据需要修改 `.env` 文件
4. 旧配置文件已自动删除：
   - ~~`Dockerfile.dev`~~ (已删除)
   - ~~`docker compose.dev.yml`~~ (已删除)
   - ~~`docker compose.cached.yml`~~ (已删除)
   - ~~`Dockerfile.optimized`~~ (已删除)

## 故障排查

### 常见问题

1. **端口冲突**：修改 `.env` 中的 PORT 配置
2. **挂载权限问题**：确保 Docker 有权访问项目目录
3. **环境变量不生效**：检查 `.env` 文件格式和路径
4. **健康检查失败**：检查服务启动状态和端口配置

### 调试命令

```bash
# 查看容器状态
docker compose ps

# 查看环境变量
docker compose config

# 查看服务日志
docker compose logs daily-digest

# 进入容器调试
docker compose exec daily-digest bash
```
