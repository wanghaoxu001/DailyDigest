#!/bin/bash

# Container Debug Script - 容器调试脚本
# 用于在容器内快速诊断系统状态

set -e

echo "🔍 每日安全快报系统 - 容器调试报告"
echo "========================================"
echo "生成时间: $(date)"
echo ""

# 1. 系统信息
echo "📋 系统信息"
echo "--------"
echo "操作系统: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo "Python版本: $(python --version)"
echo "工作目录: $(pwd)"
echo "用户: $(whoami)"
echo ""

# 2. 服务状态
echo "🚀 服务状态"
echo "--------"
if curl -s http://localhost:18899/health > /dev/null; then
    echo "✅ 服务运行正常"
    echo "健康检查响应:"
    curl -s http://localhost:18899/health | jq . 2>/dev/null || curl -s http://localhost:18899/health
else
    echo "❌ 服务无响应"
fi
echo ""

# 3. 进程状态
echo "⚙️ 进程状态"
echo "--------"
echo "Python进程:"
ps aux | grep python | grep -v grep || echo "未找到Python进程"
echo ""
echo "端口监听:"
netstat -tlnp | grep 18899 || echo "端口18899未监听"
echo ""

# 4. 资源使用
echo "📊 资源使用"
echo "--------"
echo "内存使用:"
free -h
echo ""
echo "磁盘使用:"
df -h | grep -E "(Filesystem|/app|/$)"
echo ""
echo "CPU负载:"
uptime
echo ""

# 5. 环境配置
echo "🔧 环境配置"
echo "--------"
echo "环境变量检查:"
if [ -f ".env" ]; then
    echo "✅ .env 文件存在"
else
    echo "❌ .env 文件不存在"
fi

if [ ! -z "$OPENAI_API_KEY" ]; then
    echo "✅ OPENAI_API_KEY 已设置 (长度: ${#OPENAI_API_KEY})"
else
    echo "❌ OPENAI_API_KEY 未设置"
fi

if [ ! -z "$DATABASE_URL" ]; then
    echo "✅ DATABASE_URL: $DATABASE_URL"
else
    echo "⚠️ DATABASE_URL 未设置，使用默认值"
fi
echo ""

# 6. 数据库状态
echo "🗄️ 数据库状态"
echo "--------"
if [ -f "daily_digest.db" ]; then
    echo "✅ 数据库文件存在"
    echo "数据库大小: $(ls -lh daily_digest.db | awk '{print $5}')"
    echo "表结构:"
    sqlite3 daily_digest.db ".tables" 2>/dev/null || echo "无法连接到数据库"
else
    echo "❌ 数据库文件不存在"
fi
echo ""

# 7. 日志状态
echo "📝 日志状态"
echo "--------"
if [ -d "data/logs" ]; then
    echo "日志目录内容:"
    ls -la data/logs/ 2>/dev/null || echo "日志目录为空或不可访问"
    echo ""
    echo "最新应用日志 (最后10行):"
    if [ -f "data/logs/daily_digest.log" ]; then
        tail -n 10 data/logs/daily_digest.log
    else
        echo "应用日志文件不存在"
    fi
else
    echo "❌ 日志目录不存在"
fi
echo ""

# 8. 网络连接测试
echo "🌐 网络连接测试"
echo "--------"
echo "测试外部连接:"
if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
    echo "✅ 外网连接正常"
else
    echo "❌ 外网连接失败"
fi

if curl -s --connect-timeout 5 https://api.openai.com > /dev/null; then
    echo "✅ OpenAI API 连接正常"
else
    echo "❌ OpenAI API 连接失败"
fi
echo ""

# 9. Python模块检查
echo "🐍 Python模块检查"
echo "--------"
modules=("fastapi" "uvicorn" "sqlalchemy" "openai" "playwright" "requests")
for module in "${modules[@]}"; do
    if python -c "import $module" 2>/dev/null; then
        version=$(python -c "import $module; print(getattr($module, '__version__', 'unknown'))" 2>/dev/null)
        echo "✅ $module ($version)"
    else
        echo "❌ $module 未安装或导入失败"
    fi
done
echo ""

# 10. 安全检查
echo "🔒 安全检查"
echo "--------"
echo "文件权限:"
ls -la .env 2>/dev/null || echo ".env 文件不存在"
ls -la daily_digest.db 2>/dev/null || echo "数据库文件不存在"
echo "数据目录权限:"
ls -la data/ 2>/dev/null || echo "数据目录不存在"
echo ""

# 11. 快速诊断建议
echo "💡 快速诊断建议"
echo "--------"
if ! curl -s http://localhost:18899/health > /dev/null; then
    echo "🔧 服务未运行，尝试手动启动:"
    echo "   python run.py"
fi

if [ ! -f ".env" ]; then
    echo "🔧 缺少配置文件，请复制环境模板:"
    echo "   cp envtemplate.txt .env"
fi

if [ -z "$OPENAI_API_KEY" ]; then
    echo "🔧 请设置 OpenAI API Key:"
    echo "   export OPENAI_API_KEY=your_key_here"
fi

echo ""
echo "✅ 调试报告生成完成！"
echo ""
echo "🛠️ 更多调试工具:"
echo "   htop          # 系统监控"
echo "   tail -f data/logs/daily_digest.log  # 实时日志"
echo "   sqlite3 daily_digest.db  # 数据库客户端"
echo "   tree -L 3     # 目录结构" 