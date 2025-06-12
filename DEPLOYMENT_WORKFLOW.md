# DailyDigest 部署工作流指南

## 🎯 问题解决

### 原问题
- `docker compose down && docker compose up` 后代码没有更新
- 需要手动重新构建镜像才能看到代码变更

### 解决方案
我们提供了**开发环境**和**生产环境**两套配置，解决不同场景的需求。

## 🔧 开发环境（推荐用于代码调试）

### 特点
- ✅ **代码挂载**：本地代码直接挂载到容器，修改立即生效
- ✅ **快速重启**：只需重启容器，无需重新构建镜像
- ✅ **实时调试**：支持代码热更新

### 使用方法

```bash
# 1. 首次部署（构建镜像 + 启动）
./scripts/deploy.sh dev

# 2. 代码更新后的快速重启
./scripts/quick-restart.sh

# 3. 依赖文件更新（requirements.txt变更）
./scripts/update-deps.sh

# 4. 手动操作（如果需要）
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up -d
```

## 🏭 生产环境（用于正式部署）

### 特点
- ✅ **代码内置**：代码打包在镜像中，更安全稳定
- ✅ **版本固定**：每次部署创建新镜像，便于版本管理
- ✅ **性能最优**：无挂载开销

### 使用方法

```bash
# 生产环境部署（强制重新构建）
./scripts/deploy.sh prod

# 手动操作（如果需要）
docker compose down
docker compose build --no-cache
docker compose up -d
```

## 📋 推荐工作流

### 日常开发工作流

```bash
# 1. 本地修改代码
git add .
git commit -m "修改说明"
git push origin main

# 2. 服务器拉取并部署
cd /path/to/DailyDigest
./scripts/deploy.sh dev

# 3. 后续工作流程：
# 3a. 只有代码修改时（最快）
git pull origin main
./scripts/quick-restart.sh

# 3b. 依赖文件变更时
git pull origin main
./scripts/update-deps.sh

# 3c. 大更新时（重新构建）
git pull origin main
./scripts/deploy.sh dev
```

### 生产发布工作流

```bash
# 1. 确保代码已推送到主分支
git pull origin main

# 2. 生产环境部署
./scripts/deploy.sh prod

# 3. 验证服务
curl http://localhost:18899/health
```

## 🗂️ 文件结构说明

```
DailyDigest/
├── docker-compose.yml          # 生产环境配置
├── docker-compose.dev.yml      # 开发环境配置（代码挂载）
├── Dockerfile                  # 生产环境镜像
├── Dockerfile.dev             # 开发环境镜像
├── requirements.txt            # Python依赖文件（挂载，立即生效）
└── scripts/
    ├── deploy.sh              # 自动化部署脚本
    ├── quick-restart.sh       # 快速重启脚本
    └── update-deps.sh         # 依赖更新脚本
```

## 🎯 核心区别

| 特性 | 开发环境 | 生产环境 |
|------|----------|----------|
| 代码位置 | 挂载 (`-v .:/app`) | 内置 (`COPY . .`) |
| 代码更新 | 立即生效 | 需重新构建 |
| 重启速度 | 快 (3-5秒) | 慢 (30-60秒) |
| 安全性 | 中等 | 高 |
| 调试便利性 | 高 | 低 |

## ⚡ 性能优化建议

### 开发环境优化
- 使用 `.dockerignore` 减少挂载的文件
- 禁用不必要的健康检查
- 使用本地缓存加速构建

### 生产环境优化
- 多阶段构建减少镜像大小
- 使用镜像缓存加速重新构建
- 配置合适的健康检查间隔

## 🐛 常见问题

### Q: 开发环境下修改代码后为什么没有生效？
A: 
1. 确认使用的是 `docker-compose.dev.yml`
2. 检查代码挂载是否正确：`docker compose -f docker-compose.dev.yml exec daily-digest ls -la /app`
3. 如果是普通代码修改：`./scripts/quick-restart.sh`
4. 如果是依赖文件修改：`./scripts/update-deps.sh`

### Q: 修改了 requirements.txt 但新依赖没有安装？
A: 
1. 使用依赖更新脚本：`./scripts/update-deps.sh`
2. 或者重新部署：`./scripts/deploy.sh dev`

### Q: 为什么生产环境要重新构建镜像？
A: 生产环境将代码打包在镜像中，确保部署的一致性和安全性。

### Q: 如何查看容器日志？
A:
```bash
# 开发环境
docker compose -f docker-compose.dev.yml logs daily-digest

# 生产环境
docker compose logs daily-digest
```

## 🎉 最佳实践

1. **开发阶段**：使用开发环境配置，享受快速迭代
2. **测试阶段**：使用生产环境配置，确保部署一致性
3. **生产部署**：使用生产环境配置，保证稳定性
4. **定期清理**：清理不用的镜像和容器释放空间

```bash
# 清理命令
docker system prune -f
docker image prune -f
``` 