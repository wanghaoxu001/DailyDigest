# DailyDigest Agent Playbook

## 回答语言
- 所有对话一律使用简体中文；如需列举命令或代码段，保留原始英文/符号。

## 项目速览
- 后端基于 FastAPI (`app/main.py`)，启动时通过 `lifespan` 初始化数据库、同步 Cron、准备日志。
- 数据存储采用 SQLAlchemy + SQLite (`app/db/` 与 `daily_digest.db`)，`Base.metadata.create_all` 与迁移脚本共同维护 schema。
- 新闻采集与处理在 `app/crawlers/`、`app/services/` 中协作：爬虫抓取 → `llm_processor` 调用 OpenAI/GPT → `news_similarity` 去重 → `digest_generator` 生成 Markdown/PDF。
- APScheduler 与自定义 `cron_manager` 负责定时任务，相关执行记录经 `app/api/endpoints/task_executions.py` 暴露。
- UI 使用 Jinja2 模板 + Bootstrap (`app/templates/` + `app/static/`)，`/` 提供管理界面，`/api` 提供 JSON API。

## 代码目录要点
- `app/api/endpoints/`：REST 路由，`router.py` 将新闻、快报、日志、相似度等分模块挂载。
- `app/crawlers/`：抽象基类、微信爬虫及解析器；需要 Playwright、BeautifulSoup 等依赖。
- `app/services/`：业务层，包括 LLM 处理、快报生成、相似度计算、Cron 管理、Playwright PDF 等。
- `app/models/`：SQLAlchemy ORM 定义（新闻、来源、快报、任务记录等）。
- `app/db/`：数据库会话、初始化、迁移与数据补丁。
- `app/config/`：日志配置与全局 `get_logger`。
- `templates/`、`static/`：前端模板与资源，按功能划分子目录。
- `scripts/`：数据库维护、调试、运维脚本；`tools/` 存放一次性工具（如 `clear_news.py`）。
- `data/`：运行生成的 Markdown/PDF、日志、抓取结果；不要写入版本控制。
- 根目录含若干诊断脚本与 `test_*.py` 单测文件。

## 关键模块速记
- `app/services/llm_processor.py`：封装语言检测、OpenAI API 调用、摘要/分类解析；依赖 `.env` 中的 `OPENAI_*` 配置。
- `app/services/digest_generator.py`：按分类组装 Markdown，并调用 `playwright_pdf_generator` 生成 PDF（Chromium 必备）。
- `app/services/news_similarity.py` 与 `news_duplicate_detector.py`：以向量化/缓存方式做新闻去重，避免重复入库。
- `app/services/cron_manager.py`：同步数据库中定义的计划任务到系统 Cron，同时记录执行状态。
- `app/api/endpoints/news.py` 等：实现筛选、分组、相似度查询；注意统一使用北京时间（`pytz`）。
- `app/main.py`：额外包含代理环境 URL 解码中间件，特殊处理 PDF 下载请求。

## 常用命令
- `python -m venv venv && source venv/bin/activate`：创建并激活虚拟环境（Python 3.8+）。
- `pip install -r requirements.txt`：安装依赖（Playwright 需另行 `playwright install`）。
- `cp envtemplate.txt .env`：初始化配置，再填充 OpenAI、数据库、调度相关变量。
- `python run.py`：启动 FastAPI 服务，执行迁移、加载 Cron、开启调度器。
- `pytest`：运行根目录下的回归测试；慢测可使用 `pytest -m "not slow"`。
- `docker-compose up`：容器化启动，读取 `.env`。

## 开发规范
- 遵循 PEP 8、四空格缩进；新增代码尽量补全类型标注。
- 函数命名使用 `snake_case`，类使用 `CamelCase`，异步处理器建议 `async_` 前缀。
- 模板与静态资源按功能归档（例如 `app/templates/digest/*` 配对 `app/static/digest/*`）。
- 注释仅在复杂逻辑前补充意图说明，避免冗余描述。

## 测试与验证
- 新增或修改业务逻辑时，在根目录添加对应 `test_*.py`；命名与目标模块匹配（如 `test_scheduler.py`）。
- 网络/外部 API 调用需 stub 或注入依赖，必要时复用 `data/` 中的录制资源。
- 爬虫相关测试应标记并可通过环境变量禁用，避免 CI 长时间运行。

## 数据与安全提醒
- `.env`、数据库、PDF/Markdown 输出等敏感文件禁止提交；`data/` 仅作本地存储。
- 变更调度器、Playwright、OpenAI 配置时，更新文档/PR 说明并提醒资源占用。
- 需要使用代理或外部服务时，遵守仓库现有日志与安全策略，确保不会泄露密钥。

## 协作建议
- 提交信息采用 `feat|fix|chore(scope?): message` 形式，中英文均可但保持简洁。
- PR 需附上变更目的、验证方式（如 `pytest` 输出、手动爬虫记录、UI 截图）及对计划任务/资源的影响。
- 若遇到未知改动（非本人生成），立即暂停并向用户确认，避免误覆盖。
