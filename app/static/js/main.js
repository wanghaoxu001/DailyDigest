/**
 * 每日安全快报系统 - 主JS文件
 */

// 通用工具函数
const utils = {
    // 格式化日期
    formatDate: function(dateStr, format = 'YYYY-MM-DD') {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        
        const formatMap = {
            'YYYY': date.getFullYear(),
            'MM': String(date.getMonth() + 1).padStart(2, '0'),
            'DD': String(date.getDate()).padStart(2, '0'),
            'HH': String(date.getHours()).padStart(2, '0'),
            'mm': String(date.getMinutes()).padStart(2, '0'),
            'ss': String(date.getSeconds()).padStart(2, '0')
        };
        
        let result = format;
        for (const [key, value] of Object.entries(formatMap)) {
            result = result.replace(key, value);
        }
        
        return result;
    },
    
    // 截断文本
    truncateText: function(text, maxLength = 100) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    },
    
    // 显示加载中
    showLoading: function(container) {
        container.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
            </div>
        `;
    },
    
    // 显示错误信息
    showError: function(container, message = '加载失败') {
        container.innerHTML = `
            <div class="alert alert-danger">
                <p>${message}</p>
            </div>
        `;
    },
    
    // 获取分类标签HTML
    getCategoryBadge: function(category) {
        const categories = {
            '金融业网络安全事件': '<span class="badge bg-info">金融业</span>',
            '重大网络安全事件': '<span class="badge bg-danger">重大事件</span>',
            '重大数据泄露事件': '<span class="badge bg-warning">数据泄露</span>',
            '重大漏洞风险提示': '<span class="badge bg-primary">漏洞风险</span>',
            '其他': '<span class="badge bg-secondary">其他</span>'
        };
        
        return categories[category] || categories['其他'];
    }
};

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 绑定通用事件
    bindCommonEvents();
});

// 绑定通用事件
function bindCommonEvents() {
    // 返回顶部按钮
    const backToTopBtn = document.getElementById('backToTop');
    if (backToTopBtn) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopBtn.classList.add('show');
            } else {
                backToTopBtn.classList.remove('show');
            }
        });
        
        backToTopBtn.addEventListener('click', function() {
            window.scrollTo({top: 0, behavior: 'smooth'});
        });
    }
    
    // 工具提示初始化
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
} 