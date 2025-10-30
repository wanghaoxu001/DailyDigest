# Docker 容器调试指南

> ✅ **已更新**: 本文档已针对新的统一Docker配置进行更新，支持生产和开发环境的容器调试。

## 📦 容器内置工具

我们使用 `python:3.11` 完整镜像作为基础镜像，并安装了丰富的调试和开发工具，方便在容器内进行问题排查。

### 🛠️ 已安装的调试工具

#### 基础开发工具
- **vim/nano** - 文本编辑器
- **git** - 版本控制
- **tree** - 目录结构查看
- **less** - 分页查看文件

#### 网络调试工具
- **curl/wget** - HTTP 请求测试
- **ping** - 网络连通性测试
- **telnet** - 端口连接测试
- **netcat (nc)** - 网络调试利器
- **nmap** - 网络扫描工具
- **net-tools** - 网络配置工具 (ifconfig, netstat 等)

#### 系统监控工具
- **htop** - 进程监控
- **ps** - 进程查看
- **lsof** - 文件和端口占用查看
- **strace** - 系统调用跟踪

#### 文件处理工具
- **zip/unzip** - 压缩解压
- **tar/gzip** - 打包压缩
- **jq** - JSON 处理
- **sqlite3** - SQLite 数据库客户端

## 🔍 常用调试命令

### 1. 进入容器进行调试

```bash
# 进入运行中的容器 (生产环境)
docker compose exec daily-digest bash

# 进入运行中的容器 (开发环境)  
docker compose --profile dev exec daily-digest-dev bash

# 或者启动一个新的调试容器
docker run -it --rm \
    -v $(pwd):/app \
    -v $(pwd)/data:/app/data \
    --env-file .env \
    daily-digest bash
```

### 2. 网络连接调试

```bash
# 测试外部API连接
curl -I https://api.openai.com/v1/models

# 测试内部服务
curl http://localhost:18899/health

# 检查端口监听
netstat -tlnp | grep 18899

# 测试端口连接
telnet localhost 18899
```

### 3. 系统资源监控

```bash
# 查看系统资源使用
htop

# 查看进程列表
ps aux | grep python

# 查看内存使用
free -h

# 查看磁盘使用
df -h

# 查看文件句柄使用
lsof | grep python
```

### 4. 应用日志查看

```bash
# 查看应用日志
tail -f data/logs/daily_digest.log

# 查看错误日志
tail -f data/logs/errors.log

# 搜索特定错误
grep -i "error" data/logs/*.log

# 实时监控日志
tail -f data/logs/*.log
```

### 5. 数据库调试

```bash
# 连接SQLite数据库
sqlite3 daily_digest.db

# 查看表结构
.schema

# 查看数据
SELECT * FROM sources LIMIT 5;
SELECT * FROM news ORDER BY created_at DESC LIMIT 10;

# 退出数据库
.quit
```

### 6. Python 环境调试

```bash
# 检查Python环境
python --version
pip list

# 测试模块导入
python -c "from app.main import app; print('✅ 应用导入成功')"

# 检查依赖
python -c "import playwright; print('✅ Playwright 可用')"
python -c "import openai; print('✅ OpenAI 可用')"

# 启动Python交互式环境
python
```

### 7. 文件系统调试

```bash
# 查看目录结构
tree -L 3

# 查看文件权限
ls -la data/

# 查看磁盘空间
du -sh data/*

# 查找文件
find . -name "*.log" -type f
```

### 8. 进程调试

```bash
# 查看Python进程
ps aux | grep python

# 跟踪系统调用
strace -p <python_pid>

# 查看进程打开的文件
lsof -p <python_pid>
```

## 🚨 常见问题排查

### 1. 服务启动失败

```bash
# 检查配置文件
cat .env

# 检查环境变量
env | grep OPENAI

# 手动启动服务查看错误
python run.py
```

### 2. 网络连接问题

```bash
# 测试DNS解析
nslookup api.openai.com

# 测试网络连通性
ping api.openai.com

# 检查防火墙规则
iptables -L
```

### 3. 数据库连接问题

```bash
# 检查数据库文件
ls -la daily_digest.db

# 测试数据库连接
sqlite3 daily_digest.db ".tables"

# 检查数据库权限
ls -la daily_digest.db
```

### 4. 内存和性能问题

```bash
# 查看内存使用
free -h

# 查看进程内存使用
ps aux --sort=-%mem | head

# 查看系统负载
uptime

# 查看I/O统计
iostat 1
```

## 🔧 调试技巧

### 1. 容器内开发

```bash
# 在容器内修改代码
vim app/services/crawler.py

# 重启服务测试
pkill python
python run.py &
```

### 2. 日志实时监控

```bash
# 查看Docker容器日志
# 生产环境
docker compose logs -f daily-digest

# 开发环境
docker compose --profile dev logs -f daily-digest-dev

# 多窗口监控
# 终端1: 查看应用日志
tail -f data/logs/daily_digest.log

# 终端2: 查看系统资源
htop

# 终端3: 进行操作测试
curl http://localhost:18899/health
```

### 3. 网络抓包

```bash
# 使用tcpdump抓包 (需要特权模式)
docker run --privileged --net=host ...

# 或者使用netcat测试
nc -zv api.openai.com 443
```

### 4. 性能分析

```bash
# Python性能分析
python -m cProfile run.py

# 内存使用分析
python -c "
import tracemalloc
tracemalloc.start()
# 运行代码
current, peak = tracemalloc.get_traced_memory()
print(f'当前内存: {current / 1024 / 1024:.1f} MB')
print(f'峰值内存: {peak / 1024 / 1024:.1f} MB')
"
```

## 📱 快速调试脚本

创建 `debug.sh` 脚本：

```bash
#!/bin/bash
# debug.sh - 容器调试脚本

echo "=== 系统信息 ==="
uname -a
python --version

echo "=== 服务状态 ==="
curl -s http://localhost:18899/health | jq .

echo "=== 进程状态 ==="
ps aux | grep python

echo "=== 内存使用 ==="
free -h

echo "=== 磁盘使用 ==="
df -h

echo "=== 网络连接 ==="
netstat -tlnp | grep 18899

echo "=== 最新日志 ==="
tail -n 20 data/logs/daily_digest.log
```

使用方法：

```bash
# 在容器内运行
chmod +x debug.sh
./debug.sh
```

这样您就可以在容器内方便地进行各种调试和问题排查了！ 🔍 