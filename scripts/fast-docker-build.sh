#!/bin/bash

# 快速Docker构建脚本 - 统一配置版本
# 使用新的统一Dockerfile和profile配置

set -e

echo "🚀 启动快速Docker构建（统一配置版本）..."

# 启用BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 检查Docker版本
print_step "检查Docker环境..."
if ! docker buildx version >/dev/null 2>&1; then
    print_warning "Docker BuildKit不可用，使用标准构建"
    export DOCKER_BUILDKIT=0
    export COMPOSE_DOCKER_CLI_BUILD=0
else
    print_success "Docker BuildKit已启用"
fi

# 检查是否存在环境配置文件
if [ ! -f ".env" ]; then
    print_warning "未找到.env文件，创建默认配置..."
    if [ -f "env.example" ]; then
        cp env.example .env
        print_success "已从env.example创建.env文件"
    else
        echo "BUILD_ENV=development" > .env
        echo "FLASK_ENV=development" >> .env
        print_success "已创建基础.env文件"
    fi
fi

# 选择构建类型
while true; do
    echo ""
    echo "请选择构建类型："
    echo "1) 开发环境 (推荐) - 代码挂载，快速开发"
    echo "2) 生产环境 - 完整构建，代码内置"
    echo "3) 重建缓存 - 更新依赖和镜像"
    read -p "请输入选择 [1-3]: " choice
    
    case $choice in
        1)
            BUILD_TYPE="dev"
            BUILD_ENV="development"
            PROFILE="--profile dev"
            SERVICE_NAME="daily-digest-dev"
            break
            ;;
        2)
            BUILD_TYPE="prod"
            BUILD_ENV="production"
            PROFILE=""
            SERVICE_NAME="daily-digest"
            break
            ;;
        3)
            BUILD_TYPE="cache"
            BUILD_ENV="development"
            PROFILE="--profile dev"
            SERVICE_NAME="daily-digest-dev"
            break
            ;;
        *)
            print_error "无效选择，请输入1-3"
            ;;
    esac
done

# 更新环境变量文件
sed -i.bak "s/BUILD_ENV=.*/BUILD_ENV=$BUILD_ENV/" .env 2>/dev/null || true
if [ "$BUILD_ENV" = "development" ]; then
    sed -i.bak "s/FLASK_ENV=.*/FLASK_ENV=development/" .env 2>/dev/null || true
else
    sed -i.bak "s/FLASK_ENV=.*/FLASK_ENV=production/" .env 2>/dev/null || true
fi

# 显示估算的构建时间
case $BUILD_TYPE in
    "dev")
        print_step "开发环境构建 - 预计时间：2-5分钟（首次），30秒-2分钟（后续）"
        ;;
    "prod")
        print_step "生产环境构建 - 预计时间：8-15分钟（首次），3-5分钟（后续）"
        ;;
    "cache")
        print_step "缓存重建 - 预计时间：5-10分钟"
        ;;
esac

# 显示优化信息
echo ""
print_step "使用的优化策略："
echo "  • 统一的Dockerfile配置"
echo "  • 环境变量控制构建类型"
echo "  • Docker BuildKit缓存"
echo "  • 智能层缓存优化"
echo "  • pip缓存持久化"
echo "  • Playwright浏览器缓存复用"

# 开始构建
echo ""
print_step "开始构建（BUILD_ENV=$BUILD_ENV）..."

# 记录开始时间
start_time=$(date +%s)

if [ "$BUILD_TYPE" = "cache" ]; then
    print_step "重建缓存（无缓存构建）..."
    docker compose $PROFILE build --no-cache --pull $SERVICE_NAME
else
    # 使用缓存构建
    docker compose $PROFILE build --pull $SERVICE_NAME
fi

# 计算构建时间
end_time=$(date +%s)
build_time=$((end_time - start_time))
build_minutes=$((build_time / 60))
build_seconds=$((build_time % 60))

print_success "构建完成！耗时：${build_minutes}分${build_seconds}秒"

# 提供启动建议
echo ""
print_step "启动建议："
if [ "$BUILD_TYPE" = "dev" ]; then
    echo "  • 启动容器：docker compose --profile dev up -d"
    echo "  • 查看日志：docker compose --profile dev logs -f daily-digest-dev"
    echo "  • 进入容器：docker compose --profile dev exec daily-digest-dev bash"
    echo "  • 快速重启：./scripts/quick-restart.sh"
else
    echo "  • 启动容器：docker compose up -d"
    echo "  • 查看日志：docker compose logs -f daily-digest"
    echo "  • 进入容器：docker compose exec daily-digest bash"
fi

# 询问是否立即启动
read -p "是否立即启动容器？[y/N]: " start_now
if [[ $start_now =~ ^[Yy]$ ]]; then
    print_step "启动容器..."
    docker compose $PROFILE up -d $SERVICE_NAME
    print_success "容器已启动！访问 http://localhost:18899"
    
    # 等待服务启动
    print_step "等待服务启动..."
    sleep 5
    
    # 检查服务健康状态
    for i in {1..5}; do
        if curl -f http://localhost:18899/health >/dev/null 2>&1; then
            print_success "服务健康检查通过！"
            break
        fi
        echo "等待服务启动... ($i/5)"
        sleep 2
    done
    
    # 显示容器状态
    echo ""
    print_step "容器状态："
    docker compose $PROFILE ps
fi

echo ""
print_success "快速构建脚本执行完成！"
print_step "配置摘要："
echo "  • 构建环境：$BUILD_ENV"
echo "  • 服务名称：$SERVICE_NAME"
echo "  • Profile：${PROFILE:-default}"
echo "  • 配置文件：docker compose.yml"