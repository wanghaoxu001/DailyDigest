/**
 * 每日安全快报系统 - 新闻页面脚本
 * 性能优化版本
 */

// ==================== 工具函数 ====================

/**
 * 防抖函数 - 延迟执行，只在最后一次调用后执行
 */
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数 - 限制执行频率
 */
function throttle(func, limit = 100) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * 使用requestAnimationFrame优化的滚动处理
 */
function rafThrottle(callback) {
    let rafId = null;
    return function(...args) {
        if (rafId === null) {
            rafId = requestAnimationFrame(() => {
                callback.apply(this, args);
                rafId = null;
            });
        }
    };
}

// ==================== 全局变量 ====================

let selectedNews = new Set();
let currentNewsId = null;
let excludedSources = new Map();
let totalArticles = 0;
let articleElements = [];
const CACHE_KEY = 'dailydigest_selected_news';

// ==================== DOM就绪处理 ====================

document.addEventListener('DOMContentLoaded', function() {
    // 设置今天的日期
    const today = new Date();
    document.getElementById('digestDate').valueAsDate = today;

    // 配置marked.js
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true
        });
    }

    // 初始化tooltip
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(tooltipTriggerEl => {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 加载数据
    loadSources();
    loadNews();
    
    // 延迟恢复缓存
    setTimeout(loadSelectionFromCache, 500);

    // 绑定事件 - 使用防抖优化
    bindEvents();

    // 初始化滚动进度监听器
    initScrollProgress();
});

// ==================== 事件绑定 ====================

function bindEvents() {
    // 防抖的loadNews函数
    const debouncedLoadNews = debounce(loadNews, 300);
    
    // 分类筛选 - 使用防抖
    document.querySelectorAll('.category-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            updateCategoryCount();
            debouncedLoadNews();
        });
    });

    // 来源筛选 - 使用防抖
    document.getElementById('sourceFilter').addEventListener('change', debouncedLoadNews);
    
    // 时间范围 - 使用防抖
    document.getElementById('timeRange').addEventListener('change', function() {
        updateTimeRangeDescription();
        debouncedLoadNews();
    });

    // 显示选项 - 使用防抖
    document.getElementById('excludeUsed').addEventListener('change', debouncedLoadNews);

    // 排除来源
    document.getElementById('excludeSourceSelect').addEventListener('change', function() {
        if (this.value) {
            addExcludedSource(this.value, this.options[this.selectedIndex].text);
            this.value = '';
            debouncedLoadNews();
        }
    });

    document.getElementById('btnClearExcludedSources').addEventListener('click', function() {
        clearAllExcludedSources();
        loadNews();
    });

    // 分类全选/全不选
    document.getElementById('btnSelectAllCategories').addEventListener('click', function() {
        document.querySelectorAll('.category-checkbox').forEach(checkbox => {
            checkbox.checked = true;
        });
        updateCategoryCount();
        loadNews();
    });

    document.getElementById('btnDeselectAllCategories').addEventListener('click', function() {
        document.querySelectorAll('.category-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
        updateCategoryCount();
        loadNews();
    });

    // 初始化计数
    updateCategoryCount();
    updateTimeRangeDescription();

    // 生成快报按钮 - 防止重复点击
    const btnGenerateDigest = document.getElementById('btnGenerateDigest');
    const btnGenerateDigestBottom = document.getElementById('btnGenerateDigestBottom');
    const btnConfirmGenerate = document.getElementById('btnConfirmGenerate');
    
    btnGenerateDigest.addEventListener('click', showGenerateDigestModal);
    btnGenerateDigestBottom.addEventListener('click', showGenerateDigestModal);
    btnConfirmGenerate.addEventListener('click', function() {
        // 防止重复提交
        if (this.disabled) return;
        this.disabled = true;
        generateDigest();
    });
}

// ==================== 缓存管理 ====================

function saveSelectionToCache() {
    try {
        const selectedArray = Array.from(selectedNews);
        localStorage.setItem(CACHE_KEY, JSON.stringify(selectedArray));
        console.log('已保存勾选缓存:', selectedArray.length, '条新闻');
    } catch (error) {
        console.error('保存勾选缓存失败:', error);
    }
}

function loadSelectionFromCache() {
    try {
        const cached = localStorage.getItem(CACHE_KEY);
        if (cached) {
            const selectedArray = JSON.parse(cached);
            console.log('正在恢复勾选缓存:', selectedArray.length, '条新闻');
            selectedArray.forEach(id => selectedNews.add(id));
            updateSelectionUI();
        }
    } catch (error) {
        console.error('加载勾选缓存失败:', error);
        localStorage.removeItem(CACHE_KEY);
    }
}

function clearSelectionCache() {
    try {
        localStorage.removeItem(CACHE_KEY);
        console.log('已清除勾选缓存');
    } catch (error) {
        console.error('清除勾选缓存失败:', error);
    }
}

function updateSelectionUI() {
    document.getElementById('selectedCount').textContent = selectedNews.size;
    document.getElementById('selectedCountBottom').textContent = selectedNews.size;
    document.getElementById('btnGenerateDigest').disabled = selectedNews.size === 0;
    document.getElementById('btnGenerateDigestBottom').disabled = selectedNews.size === 0;
}

// ==================== UI更新函数 ====================

function updateCategoryCount() {
    const selectedCount = document.querySelectorAll('.category-checkbox:checked').length;
    document.getElementById('selectedCategoriesCount').textContent = selectedCount;
}

function updateTimeRangeDescription() {
    const timeRange = document.getElementById('timeRange').value;
    const descriptionEl = document.getElementById('timeRangeDescription');
    
    if (timeRange === 'since_yesterday_digest') {
        descriptionEl.style.display = 'block';
        descriptionEl.innerHTML = '<i class="bi bi-clock-history"></i> 正在获取昨天快报时间...';
        
        axios.get('/api/digest/yesterday/last-created')
            .then(response => {
                if (response.data.has_digest) {
                    const digestTime = new Date(response.data.last_digest_time);
                    const formattedTime = digestTime.toLocaleString('zh-CN', {
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        timeZone: 'Asia/Shanghai'
                    });
                    descriptionEl.innerHTML = `<i class="bi bi-check-circle text-success"></i> 自 ${formattedTime} 以后的新闻`;
                } else {
                    descriptionEl.innerHTML = '<i class="bi bi-info-circle text-warning"></i> 昨天没有生成快报，将显示昨天00:00以后的新闻';
                }
            })
            .catch(error => {
                console.error('获取昨天快报时间失败:', error);
                descriptionEl.innerHTML = '<i class="bi bi-exclamation-triangle text-danger"></i> 无法获取快报时间，使用默认范围';
            });
    } else {
        descriptionEl.style.display = 'none';
    }
}

// ==================== 排除来源管理 ====================

function addExcludedSource(sourceId, sourceName) {
    excludedSources.set(sourceId, sourceName);
    updateExcludedSourcesDisplay();
    updateExcludeSourceSelect();
}

function removeExcludedSource(sourceId) {
    excludedSources.delete(sourceId);
    updateExcludedSourcesDisplay();
    updateExcludeSourceSelect();
    loadNews();
}

function clearAllExcludedSources() {
    excludedSources.clear();
    updateExcludedSourcesDisplay();
    updateExcludeSourceSelect();
}

function updateExcludedSourcesDisplay() {
    const excludedRow = document.getElementById('excludedSourcesRow');
    const excludedList = document.getElementById('excludedSourcesList');
    
    if (excludedSources.size > 0) {
        excludedRow.style.display = 'block';
        const tags = Array.from(excludedSources.entries()).map(([id, name]) => 
            `<span class="badge bg-warning text-dark me-1" style="cursor: pointer;" onclick="removeExcludedSource('${id}')">
                ${name} <i class="bi bi-x"></i>
            </span>`
        ).join('');
        excludedList.innerHTML = tags;
    } else {
        excludedRow.style.display = 'none';
    }
}

function updateExcludeSourceSelect() {
    const excludeSelect = document.getElementById('excludeSourceSelect');
    
    while (excludeSelect.children.length > 1) {
        excludeSelect.removeChild(excludeSelect.lastChild);
    }
    
    axios.get('/api/sources/')
        .then(response => {
            const sources = response.data;
            sources.forEach(source => {
                if (!excludedSources.has(source.id.toString())) {
                    const option = document.createElement('option');
                    option.value = source.id;
                    option.textContent = source.name;
                    excludeSelect.appendChild(option);
                }
            });
        })
        .catch(error => {
            console.error('Error loading sources for exclude select:', error);
        });
}

// ==================== 数据加载 ====================

function loadSources() {
    axios.get('/api/sources/')
        .then(response => {
            const sources = response.data;
            const sourceFilter = document.getElementById('sourceFilter');
            const excludeSourceSelect = document.getElementById('excludeSourceSelect');

            sources.forEach(source => {
                const option = document.createElement('option');
                option.value = source.id;
                option.textContent = source.name;
                sourceFilter.appendChild(option);

                const excludeOption = document.createElement('option');
                excludeOption.value = source.id;
                excludeOption.textContent = source.name;
                excludeSourceSelect.appendChild(excludeOption);
            });

            updateExcludedSourcesDisplay();
        })
        .catch(error => {
            console.error('Error loading sources:', error);
        });
}

function loadNews() {
    const selectedCategories = Array.from(document.querySelectorAll('.category-checkbox:checked'))
        .map(checkbox => checkbox.value);
    const sourceId = document.getElementById('sourceFilter').value;
    const excludedSourceIds = Array.from(excludedSources.keys());
    const hours = document.getElementById('timeRange').value;
    const excludeUsed = document.getElementById('excludeUsed').checked;

    // 显示骨架屏加载状态
    document.getElementById('newsContainer').innerHTML = `
        <div class="col-12">
            <div class="loading-container text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div class="mt-3">
                    <h5 class="text-muted">正在加载新闻...</h5>
                    <p class="text-secondary">请稍候，正在筛选符合条件的资讯</p>
                </div>
            </div>
        </div>
    `;

    if (selectedCategories.length === 0) {
        document.getElementById('newsContainer').innerHTML = `
            <div class="col-12">
                <div class="loading-container text-center">
                    <div class="alert alert-info d-inline-block">
                        <i class="bi bi-info-circle me-2"></i> 请至少选择一个分类来查看新闻
                    </div>
                </div>
            </div>
        `;
        updateNewsStatsInfo(0, 'no-category');
        updateArticleCount(0);
        return;
    }

    // 构建API URL - 统一使用 /api/news/recent 端点
    let url = '/api/news/recent?limit=1000';

    if (hours === 'since_yesterday_digest') {
        url += '&since_yesterday_digest=true&hours=24';
    } else {
        url += `&hours=${hours}`;
    }

    selectedCategories.forEach(category => {
        url += `&category=${encodeURIComponent(category)}`;
    });

    if (sourceId) url += `&source_id=${sourceId}`;

    excludedSourceIds.forEach(sourceId => {
        url += `&exclude_source_id=${sourceId}`;
    });

    if (excludeUsed) url += `&exclude_used=true`;

    axios.get(url)
        .then(response => {
            const container = document.getElementById('newsContainer');
            container.innerHTML = '';
            renderListNews(response.data, container);
        })
        .catch(error => {
            console.error('Error loading news:', error);
            document.getElementById('newsContainer').innerHTML = `
                <div class="col-12 text-center py-5">
                    <p class="text-danger">加载新闻失败: ${error.message}</p>
                </div>
            `;
            updateNewsStatsInfo(0, 'error');
            updateArticleCount(0);
        });
}

// ==================== 渲染函数 ====================

function renderListNews(data, container) {
    const { items } = data;

    if (items.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center py-5">
                <p class="text-muted">没有找到符合条件的新闻</p>
            </div>
        `;
        updateNewsStatsInfo(0, 'list');
        updateArticleCount(0);
        return;
    }

    updateNewsStatsInfo(items.length, 'list');
    updateArticleCount(items.length);
    
    items.forEach(news => {
        renderNewsCard(news, container);
    });
}

function renderNewsCard(news, container) {
    const isSelected = selectedNews.has(news.id);
    const card = document.createElement('div');
    card.className = 'col-12 mb-3';

    card.innerHTML = `
        <div class="card news-card ${isSelected ? 'selected' : ''}" data-id="${news.id}">
            <div class="reading-indicator"></div>
            <div class="card-body">
                <span class="category-badge">${getCategoryBadge(news.category)}</span>
                <h5 class="card-title">
                    ${news.generated_title || news.title}
                    ${news.summary_source ?
                      (news.summary_source === 'original'
                        ? '<i class="fas fa-quote-left text-info ms-2" title="来自原文摘要"></i>'
                        : '<i class="fas fa-robot text-primary ms-2" title="AI生成总结"></i>')
                      : ''}
                </h5>
                <p class="card-text summary-text">${truncateSummary(news.generated_summary || news.summary, 150)}</p>
            </div>
            <div class="card-footer bg-transparent">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="text-muted small">
                        <div><i class="bi bi-building text-secondary"></i> 来源: ${news.source_name || '未知来源'}</div>
                        <div class="mt-1">${formatTimeInfo(news)}</div>
                    </div>
                    ${news.tokens_usage && news.is_processed ?
                        `<small class="text-primary" title="此文章的AI处理消耗了 ${calculateTotalTokens(news.tokens_usage)} 个tokens">
                            <i class="bi bi-cpu"></i> ${calculateTotalTokens(news.tokens_usage)} tokens
                        </small>` : ''}
                </div>
                <div>
                    <button class="btn btn-sm btn-outline-primary btn-view" data-id="${news.id}">查看详情</button>
                    <button class="btn btn-sm ${isSelected ? 'btn-success' : 'btn-outline-success'} btn-select" data-id="${news.id}">
                        ${isSelected ? '✓ 已选择' : '选择'}
                    </button>
                </div>
            </div>
        </div>
    `;
    container.appendChild(card);

    card.querySelector('.btn-view').addEventListener('click', function() {
        viewNews(this.getAttribute('data-id'));
    });

    card.querySelector('.btn-select').addEventListener('click', function() {
        toggleSelectNews(this.getAttribute('data-id'));
    });
}


function renderStandaloneNews(news) {
    const container = document.getElementById('newsContainer');
    const isSelected = selectedNews.has(news.id);
    
    const newsCard = document.createElement('div');
    newsCard.className = 'col-12 mb-3';
    newsCard.innerHTML = `
        <div class="card news-card ${isSelected ? 'selected' : ''}" data-id="${news.id}">
            <div class="reading-indicator"></div>
            <div class="card-body">
                <span class="category-badge">${getCategoryBadge(news.category)}</span>
                <h5 class="card-title">
                    ${news.generated_title || news.title}
                    ${news.summary_source ? 
                      (news.summary_source === 'original' 
                        ? '<i class="fas fa-quote-left text-info ms-2" title="来自原文摘要"></i>' 
                        : '<i class="fas fa-robot text-primary ms-2" title="AI生成总结"></i>') 
                      : ''}
                </h5>
                <p class="card-text summary-text">${truncateSummary(news.generated_summary || news.summary, 150)}</p>
            </div>
            <div class="card-footer bg-transparent">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="text-muted small">
                        <div><i class="bi bi-building text-secondary"></i> 来源: ${news.source_name || '未知来源'}</div>
                        <div class="mt-1">${formatTimeInfo(news)}</div>
                    </div>
                    ${news.tokens_usage && news.is_processed ? 
                        `<small class="text-primary" title="此文章的AI处理消耗了 ${calculateTotalTokens(news.tokens_usage)} 个tokens">
                            <i class="bi bi-cpu"></i> ${calculateTotalTokens(news.tokens_usage)} tokens
                        </small>` : ''}
                </div>
                <div>
                    <button class="btn btn-sm btn-outline-primary btn-view" onclick="viewNews(${news.id})">查看详情</button>
                    <button class="btn btn-sm ${isSelected ? 'btn-success' : 'btn-outline-success'} btn-select" data-news-id="${news.id}" onclick="toggleSelectNews(${news.id})">
                        ${isSelected ? '✓ 已选择' : '选择'}
                    </button>
                </div>
            </div>
        </div>
    `;
    
    let standaloneRow = container.querySelector('.row.standalone-news');
    if (!standaloneRow) {
        standaloneRow = document.createElement('div');
        standaloneRow.className = 'row standalone-news';
        container.appendChild(standaloneRow);
    }
    
    standaloneRow.appendChild(newsCard);
}

// ==================== 新闻操作 ====================

function viewNews(newsId) {
    currentNewsId = newsId;

    axios.get(`/api/news/${newsId}`)
        .then(response => {
            const news = response.data;
            const detailContent = document.getElementById('newsDetailContent');

            let entitiesHtml = '';
            if (news.entities) {
                entitiesHtml = '<div class="mt-3"><h6><strong>提取的实体</strong></h6><ul>';

                if (Array.isArray(news.entities)) {
                    news.entities.forEach(entity => {
                        if (typeof entity === 'object' && entity !== null) {
                            if (entity.type && entity.value) {
                                entitiesHtml += `<li><strong>${entity.type}:</strong> ${entity.value}</li>`;
                            } else {
                                const entityType = Object.keys(entity)[0] || '未知类型';
                                const entityValue = entity[entityType] || '未知';
                                entitiesHtml += `<li><strong>${entityType}:</strong> ${entityValue}</li>`;
                            }
                        } else {
                            entitiesHtml += `<li>${entity}</li>`;
                        }
                    });
                } else if (typeof news.entities === 'object') {
                    if (news.entities.type && news.entities.value) {
                        entitiesHtml += `<li><strong>${news.entities.type}:</strong> ${news.entities.value}</li>`;
                    } else {
                        for (const [key, value] of Object.entries(news.entities)) {
                            if (key !== 'error') {
                                entitiesHtml += `<li><strong>${key}:</strong> ${value}</li>`;
                            }
                        }
                    }
                }

                entitiesHtml += '</ul></div>';
            }

            detailContent.innerHTML = `
            <h4>${news.title}</h4>
            <div class="text-muted mb-3">
                <div class="mb-1"><i class="bi bi-building text-secondary"></i> 来源: ${news.source_name || '未知来源'}</div>
                <div>${formatTimeInfo(news)}</div>
            </div>
            
            <div class="card mb-3">
                <div class="card-header bg-light">原始内容摘要</div>
                <div class="card-body">
                    <p>${news.summary}</p>
                    <a href="${news.original_url}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-primary">查看原文</a>
                </div>
            </div>
            
            <div class="card mb-3">
                <div class="card-header bg-light">处理结果</div>
                <div class="card-body">
                    ${news.is_processed ? `
                        <div class="mb-2"><strong>一句话标题:</strong> ${news.generated_title || '暂无'}</div>
                        <div class="mb-2"><strong>摘要:</strong> ${news.generated_summary || '暂无'}</div>
                        
                        <div class="mb-2"><strong>总结来源:</strong> 
                            ${news.summary_source === 'original' ? 
                              '<span class="badge bg-info">来自原文摘要</span>' :
                              news.summary_source === 'generated' ? 
                              '<span class="badge bg-primary">AI生成</span>' : 
                              '<span class="badge bg-secondary">未知</span>'}
                        </div>
                        
                        <div class="mb-2"><strong>文章总结状态:</strong> ${news.article_summary ? '已生成' : '未生成'}</div>
                        ${news.article_summary ? `
                        <div class="card mb-3 mt-3">
                            <div class="card-header bg-light">详细文章总结</div>
                            <div class="card-body">
                                <div class="article-summary markdown-body">${typeof DOMPurify !== 'undefined' && typeof marked !== 'undefined' ? DOMPurify.sanitize(marked.parse(news.article_summary)) : news.article_summary}</div>
                            </div>
                        </div>
                        ` : '<div class="alert alert-info mt-2">该新闻还没有生成详细文章总结，请使用"处理"功能重新处理此新闻</div>'}
                        
                        <div class="mb-2"><strong>分类:</strong> ${getCategoryLabel(news.category)}</div>
                        ${entitiesHtml}
                        
                        ${news.tokens_usage ? `
                        <div class="card mt-3">
                            <div class="card-header bg-light">Tokens使用统计</div>
                            <div class="card-body">
                                <table class="table table-sm table-striped">
                                    <thead>
                                        <tr>
                                            <th>处理类型</th>
                                            <th>Prompt Tokens</th>
                                            <th>Completion Tokens</th>
                                            <th>总计</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${formatTokensUsage(news.tokens_usage)}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        ` : ''}
                    ` : '<div class="alert alert-warning">该新闻尚未处理</div>'}
                </div>
            </div>
        `;
        
        const selectBtn = document.getElementById('btnSelectInModal');
        selectBtn.textContent = selectedNews.has(parseInt(newsId)) ? '取消选择' : '选择此新闻';
        
        selectBtn.onclick = function() {
            toggleSelectNews(newsId);
            this.textContent = selectedNews.has(parseInt(newsId)) ? '取消选择' : '选择此新闻';
        };
        
        const processBtn = document.getElementById('btnProcessInModal');
        processBtn.onclick = function() {
            processNews(newsId);
        };

        // 使用 getOrCreateInstance 避免创建多个实例导致 backdrop 残留
        const modalElement = document.getElementById('newsDetailModal');
        const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
        modal.show();
    })
    .catch(error => {
        console.error('Error loading news details:', error);
        alert('加载新闻详情失败');
    });
}

function toggleSelectNews(newsId) {
    const id = parseInt(newsId);
    
    if (selectedNews.has(id)) {
        selectedNews.delete(id);
    } else {
        selectedNews.add(id);
    }
    
    document.getElementById('selectedCount').textContent = selectedNews.size;
    document.getElementById('selectedCountBottom').textContent = selectedNews.size;
    
    document.getElementById('btnGenerateDigest').disabled = selectedNews.size === 0;
    document.getElementById('btnGenerateDigestBottom').disabled = selectedNews.size === 0;
    
    saveSelectionToCache();
    
    const allSelectBtns = document.querySelectorAll(`button[data-news-id="${id}"]`);
    allSelectBtns.forEach(btn => {
        btn.classList.toggle('btn-outline-success', !selectedNews.has(id));
        btn.classList.toggle('btn-success', selectedNews.has(id));
        btn.textContent = selectedNews.has(id) ? '已选择' : '选择';
    });
    
    const card = document.querySelector(`.news-card[data-id="${id}"]`);
    if (card) {
        card.classList.toggle('selected', selectedNews.has(id));
        
        const selectBtn = card.querySelector('.btn-select');
        if (selectBtn) {
            selectBtn.classList.toggle('btn-outline-success', !selectedNews.has(id));
            selectBtn.classList.toggle('btn-success', selectedNews.has(id));
            selectBtn.textContent = selectedNews.has(id) ? '已选择' : '选择';
        }
    }
}

function processNews(newsId) {
    const processBtn = document.getElementById('btnProcessInModal');
    processBtn.disabled = true;
    processBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';
    
    axios.post(`/api/news/${newsId}/process`)
        .then(response => {
            console.log('新闻处理完成:', response.data);
            alert('新闻处理完成，将重新加载详情');
            viewNews(newsId);
        })
        .catch(error => {
            console.error('Error processing news:', error);
            alert('处理新闻失败: ' + (error.response?.data?.detail || error.message));
        })
        .finally(() => {
            processBtn.disabled = false;
            processBtn.innerHTML = '重新处理';
        });
}


// ==================== 快报生成 ====================

function showGenerateDigestModal() {
    if (selectedNews.size === 0) {
        alert('请至少选择一条新闻');
        return;
    }

    // 使用 getOrCreateInstance 避免创建多个实例导致 backdrop 残留
    const modalElement = document.getElementById('generateDigestModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
    modal.show();
}

function generateDigest() {
    const title = document.getElementById('digestTitle').value;
    const date = document.getElementById('digestDate').value;
    const btnConfirmGenerate = document.getElementById('btnConfirmGenerate');
    
    if (!title || !date) {
        alert('请填写完整信息');
        btnConfirmGenerate.disabled = false;
        return;
    }
    
    btnConfirmGenerate.disabled = true;
    btnConfirmGenerate.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> 生成中...';
    
    const digestData = {
        title: title,
        date: new Date(date).toISOString(),
        selected_news_ids: Array.from(selectedNews)
    };
    
    axios.post('/api/digest/', digestData)
        .then(response => {
            const digestId = response.data.id;
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('generateDigestModal'));
            modal.hide();
            
            selectedNews.clear();
            document.getElementById('selectedCount').textContent = '0';
            document.getElementById('selectedCountBottom').textContent = '0';
            document.getElementById('btnGenerateDigest').disabled = true;
            document.getElementById('btnGenerateDigestBottom').disabled = true;
            
            clearSelectionCache();
            loadNews();
            
            window.location.href = `/digest/${digestId}`;
        })
        .catch(error => {
            console.error('Error generating digest:', error);
            alert('生成快报失败');
            btnConfirmGenerate.disabled = false;
            btnConfirmGenerate.innerHTML = '生成';
        });
}

// ==================== 滚动进度功能 ====================

function initScrollProgress() {
    const progressIndicator = document.getElementById('progressIndicator');
    const progressBar = document.getElementById('progressBar');
    const scrollHint = document.getElementById('scrollHint');

    let scrollTimeout;
    
    // 使用RAF优化的滚动处理
    const handleScroll = rafThrottle(() => {
        clearTimeout(scrollTimeout);
        
        if (window.scrollY > 100) {
            progressIndicator.classList.add('visible');
            document.body.classList.add('progress-visible');
        } else {
            progressIndicator.classList.remove('visible');
            document.body.classList.remove('progress-visible');
        }

        updateScrollProgress();

        scrollTimeout = setTimeout(() => {
            if (scrollHint) {
                scrollHint.style.opacity = '0.5';
            }
        }, 2000);
    });

    window.addEventListener('scroll', handleScroll, { passive: true });

    progressIndicator.addEventListener('mouseenter', function() {
        if (scrollHint) {
            scrollHint.style.opacity = '1';
        }
    });
}

function updateScrollProgress() {
    const progressBar = document.getElementById('progressBar');
    const currentArticleSpan = document.querySelector('.current-article');
    
    if (articleElements.length === 0) {
        return;
    }

    let currentArticle = 0;
    const viewportHeight = window.innerHeight;
    const scrollTop = window.scrollY;

    articleElements.forEach((element, index) => {
        const rect = element.getBoundingClientRect();
        const elementTop = scrollTop + rect.top;
        
        if (elementTop < scrollTop + viewportHeight / 2) {
            currentArticle = index + 1;
        }
    });

    const progress = (currentArticle / totalArticles) * 100;
    progressBar.style.width = `${progress}%`;
    
    currentArticleSpan.textContent = currentArticle;
    
    const scrollHint = document.getElementById('scrollHint');
    const remaining = totalArticles - currentArticle;
    if (remaining > 0) {
        scrollHint.textContent = `还有 ${remaining} 篇文章未阅读`;
    } else {
        scrollHint.textContent = '已阅读完所有文章';
    }
}

function updateArticleCount(total) {
    totalArticles = total;
    document.querySelector('.total-articles').textContent = total;
    
    const bottomActionBar = document.getElementById('bottomActionBar');
    if (total > 0) {
        bottomActionBar.style.display = 'block';
    } else {
        bottomActionBar.style.display = 'none';
    }
    
    setTimeout(() => {
        articleElements = Array.from(document.querySelectorAll('.news-card'));
        updateScrollProgress();
    }, 100);
}

// ==================== 辅助函数 ====================

function formatRelativeDate(dateStr) {
    if (!dateStr) return '';
    
    try {
        const date = new Date(dateStr);
        
        if (isNaN(date.getTime())) {
            console.warn('无效的日期字符串:', dateStr);
            return '时间格式错误';
        }
        
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffMinutes = Math.floor(diffMs / (1000 * 60));
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffMinutes < 1) {
            return '刚刚';
        } else if (diffMinutes < 60) {
            return `${diffMinutes}分钟前`;
        } else if (diffHours < 24) {
            return `${diffHours}小时前`;
        } else if (diffDays < 7) {
            return `${diffDays}天前`;
        } else {
            return formatAbsoluteDate(dateStr);
        }
    } catch (error) {
        console.error('日期格式化错误:', error, '原始字符串:', dateStr);
        return '时间解析失败';
    }
}

function formatAbsoluteDate(dateStr) {
    if (!dateStr) return '';
    
    try {
        const date = new Date(dateStr);
        
        if (isNaN(date.getTime())) {
            return '时间格式错误';
        }
        
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            timeZone: 'Asia/Shanghai'
        });
    } catch (error) {
        console.error('绝对时间格式化错误:', error);
        return '时间解析失败';
    }
}

function formatTimeInfo(news) {
    let timeInfo = '';
    
    if (news.publish_date) {
        timeInfo += `<i class="bi bi-calendar3 text-primary" title="文章发布时间"></i> 发布: ${formatAbsoluteDate(news.publish_date)}`;
    }
    
    if (news.created_at) {
        if (timeInfo) timeInfo += '<br>';
        timeInfo += `<i class="bi bi-clock text-success" title="保存到系统时间"></i> 保存: ${formatRelativeDate(news.created_at)}`;
    }
    
    return timeInfo;
}

function truncateSummary(text, maxLength = 150) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    
    const sentenceEnders = ['。', '！', '？', '.', '!', '?'];
    let bestCutoff = maxLength;
    
    for (let i = Math.min(maxLength - 20, text.length - 1); i >= Math.max(maxLength - 50, 0); i--) {
        if (sentenceEnders.includes(text[i])) {
            bestCutoff = i + 1;
            break;
        }
    }
    
    if (bestCutoff === maxLength) {
        const softBreaks = ['，', '、', ',', ' ', '；', ';'];
        for (let i = Math.min(maxLength - 10, text.length - 1); i >= Math.max(maxLength - 30, 0); i--) {
            if (softBreaks.includes(text[i])) {
                bestCutoff = i + 1;
                break;
            }
        }
    }
    
    return text.substring(0, bestCutoff).trim() + '...';
}

function getCategoryBadge(category) {
    const categories = {
        '金融业网络安全事件': '<span class="badge bg-info">金融业</span>',
        '重大网络安全事件': '<span class="badge bg-danger">重大事件</span>',
        '重大数据泄露事件': '<span class="badge bg-warning">数据泄露</span>',
        '重大漏洞风险提示': '<span class="badge bg-primary">漏洞风险</span>',
        '其他': '<span class="badge bg-secondary">其他</span>'
    };
    
    return categories[category] || categories['其他'];
}

function getCategoryLabel(category) {
    const categories = {
        '金融业网络安全事件': '金融业网络安全事件',
        '重大网络安全事件': '重大网络安全事件',
        '重大数据泄露事件': '重大数据泄露事件',
        '重大漏洞风险提示': '重大漏洞风险提示',
        '其他': '其他'
    };
    
    return categories[category] || '其他';
}

function calculateTotalTokens(tokensUsage) {
    if (!tokensUsage) return 0;
    
    let totalTokens = 0;
    for (const [type, usage] of Object.entries(tokensUsage)) {
        if (usage && typeof usage === 'object') {
            totalTokens += usage.total_tokens || 0;
        }
    }
    return totalTokens;
}

function formatTokensUsage(tokensUsage) {
    if (!tokensUsage) return '';
    
    let html = '';
    let totalPromptTokens = 0;
    let totalCompletionTokens = 0;
    let totalTokens = 0;
    
    const typeLabels = {
        'title_translation': '标题翻译',
        'summary_translation': '摘要翻译',
        'content_translation': '内容翻译',
        'article_summary': '文章总结',
        'category': '分类',
        'entities': '实体提取'
    };
    
    for (const [type, usage] of Object.entries(tokensUsage)) {
        if (!usage) continue;
        
        let promptTokens = 0;
        let completionTokens = 0;
        let tokensSum = 0;
        
        if (typeof usage === 'object') {
            promptTokens = usage.prompt_tokens || 0;
            completionTokens = usage.completion_tokens || 0;
            tokensSum = usage.total_tokens || (promptTokens + completionTokens);
            
            totalPromptTokens += promptTokens;
            totalCompletionTokens += completionTokens;
            totalTokens += tokensSum;
            
            const label = typeLabels[type] || type;
            html += `
                <tr>
                    <td>${label}</td>
                    <td>${promptTokens}</td>
                    <td>${completionTokens}</td>
                    <td>${tokensSum}</td>
                </tr>
            `;
        }
    }
    
    html += `
        <tr class="table-primary">
            <td><strong>总计</strong></td>
            <td><strong>${totalPromptTokens}</strong></td>
            <td><strong>${totalCompletionTokens}</strong></td>
            <td><strong>${totalTokens}</strong></td>
        </tr>
    `;
    
    return html;
}

function updateNewsStatsInfo(totalNews, mode) {
    const statsEl = document.getElementById('newsStatsInfo');
    if (!statsEl) return;

    let modeText = '';
    switch(mode) {
        case 'list':
            modeText = '列表模式';
            break;
        case 'error':
            modeText = '加载失败';
            break;
        case 'no-category':
            modeText = '未选择分类';
            break;
        default:
            modeText = '未知模式';
            break;
    }

    statsEl.textContent = `当前显示 ${totalNews} 条新闻 (${modeText})`;
}
