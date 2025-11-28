#!/bin/bash

# 移动端快报编辑页面假死问题修复验证脚本

echo "========================================"
echo "移动端快报编辑页面假死问题修复验证"
echo "========================================"
echo ""

# 检查修复是否已应用
echo "1. 检查修复代码是否已应用..."

# 检查全局事件初始化
if grep -q "globalEventsInitialized" /root/DailyDigest/app/templates/digest.html; then
    echo "✓ 全局事件防重复机制已应用"
else
    echo "✗ 全局事件防重复机制未找到"
fi

# 检查模态框清理
if grep -q "cleanupModalEventListeners" /root/DailyDigest/app/templates/digest.html; then
    echo "✓ 模态框事件清理机制已应用"
else
    echo "✗ 模态框事件清理机制未找到"
fi

# 检查防抖优化
if grep -q "RESIZE_THROTTLE_MS" /root/DailyDigest/app/templates/digest.html; then
    echo "✓ 防抖节流优化已应用"
else
    echo "✗ 防抖节流优化未找到"
fi

# 检查事件绑定标记
if grep -q "dataset.eventBound" /root/DailyDigest/app/templates/digest.html; then
    echo "✓ 事件防重复绑定标记已应用"
else
    echo "✗ 事件防重复绑定标记未找到"
fi

echo ""
echo "2. 启动应用服务器..."

# 检查服务是否运行
if docker ps | grep -q dailydigest; then
    echo "✓ Docker 容器正在运行"

    # 获取服务URL
    PORT=$(docker port dailydigest_app_1 8000 2>/dev/null | cut -d: -f2)
    if [ -z "$PORT" ]; then
        PORT="8000"
    fi

    echo ""
    echo "========================================"
    echo "服务访问信息"
    echo "========================================"
    echo "快报管理页面: http://localhost:$PORT/digest"
    echo ""
    echo "请使用以下方式进行测试:"
    echo ""
    echo "方法1 - Chrome 开发者工具模拟移动端:"
    echo "  1. 打开 Chrome 浏览器"
    echo "  2. 访问上述 URL"
    echo "  3. 按 F12 打开开发者工具"
    echo "  4. 点击 Toggle device toolbar (Ctrl+Shift+M)"
    echo "  5. 选择一个移动设备型号(如 iPhone 12 Pro)"
    echo "  6. 进行编辑测试"
    echo ""
    echo "方法2 - 使用真实移动设备:"
    echo "  1. 确保移动设备与电脑在同一网络"
    echo "  2. 在移动设备浏览器中访问:"
    echo "     http://<服务器IP>:$PORT/digest"
    echo ""
    echo "测试清单:"
    echo "  □ 打开快报编辑页面"
    echo "  □ 编辑快报标题"
    echo "  □ 编辑新闻摘要（快速输入大量文本）"
    echo "  □ 保存快报"
    echo "  □ 重复上述操作 5-10 次"
    echo "  □ 检查页面是否响应正常"
    echo "  □ 检查按钮点击是否有效"
    echo ""
    echo "如需查看详细日志:"
    echo "  docker logs -f dailydigest_app_1"
    echo ""

else
    echo "✗ Docker 容器未运行"
    echo ""
    echo "请先启动服务:"
    echo "  cd /root/DailyDigest"
    echo "  docker-compose up -d"
fi

echo ""
echo "详细修复报告请查看: mobile_freeze_fix_report.md"
echo "========================================"
