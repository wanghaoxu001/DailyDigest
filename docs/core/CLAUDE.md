# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily Security Digest System (每日安全快报系统) is a FastAPI-based web application that automatically crawls, processes, and generates daily security news digests using AI. The system supports multi-source news collection, intelligent deduplication, content classification, and multiple export formats.

### Project Statistics
- **Total Python Code**: ~9,225 lines across all modules
- **Database Models**: 11 core models (News, Digest, Source, EventGroup, NewsSimilarity, TaskExecution, CronConfig, etc.)
- **API Endpoints**: 30+ REST endpoints
- **Database Migrations**: 18 migration files for schema evolution
- **Technology Dependencies**: 44 Python packages
- **Supported News Sources**: RSS feeds, Web scraping, WeChat Official Accounts

## Essential Commands

### Development & Running
```bash
# Start application (local development)
python run.py

# Docker development environment
./scripts/deploy.sh dev
./scripts/quick-restart.sh  # Quick restart for development

# Docker production environment
./scripts/deploy.sh prod
```

### Environment Setup
```bash
# Create environment configuration
cp envtemplate.txt .env  # or cp env.example .env
# Edit .env file with your OpenAI API key and other settings
```

### Database Operations
```bash
# Database migrations are handled automatically on startup
# Manual migration execution:
python -m app.db.run_migrations
```

### Docker Commands
```bash
# Development with code mounting
docker compose --profile dev up -d daily-digest-dev
docker compose --profile dev logs -f daily-digest-dev

# Production deployment
docker compose up -d daily-digest
docker compose logs -f daily-digest

# View running containers
docker compose ps  # production
docker compose --profile dev ps  # development
```

### Testing & Debugging
```bash
# Health check
curl http://localhost:18899/health

# View service logs
docker compose logs daily-digest  # production
docker compose --profile dev logs daily-digest-dev  # development

# Enter container for debugging
docker compose exec daily-digest bash  # production
docker compose --profile dev exec daily-digest-dev bash  # development
```

## Architecture Overview

### Core Components

**FastAPI Application Structure:**
- `app/main.py` - Main FastAPI application with middleware, routing, and lifecycle management
- `run.py` - Application entry point with uvicorn server and database initialization
- `app/api/` - RESTful API endpoints organized by functionality
- `app/services/` - Business logic services (crawler, LLM processor, scheduler, PDF generation)
- `app/models/` - SQLAlchemy database models
- `app/db/` - Database configuration, migrations, and session management

**Key Services:**
- **Crawler Service** (`app/services/crawler.py`) - Multi-source news collection (RSS, web scraping, WeChat)
- **LLM Processor** (`app/services/llm_processor.py`) - OpenAI-based content analysis and summarization
- **Scheduler Service** (`app/services/scheduler.py`) - APScheduler-based automated tasks
- **PDF Generator** (`app/services/playwright_pdf_generator.py`) - Playwright-based PDF export
- **Duplicate Detection** (`app/services/news_duplicate_detector.py`) - Semantic similarity-based deduplication

**Data Models:**
- `News` - Individual news articles with metadata and processing status
- `Digest` - Generated daily security digests
- `Source` - News source configuration (RSS feeds, websites, WeChat accounts)
- `EventGroup` - Grouped related news events
- `NewsSimilarity` - Semantic similarity relationships between articles

### Technology Stack
- **Backend**: FastAPI + SQLAlchemy + SQLite
- **AI Processing**: OpenAI GPT API + sentence-transformers for embeddings
- **Web Scraping**: Playwright + Newspaper4k + BeautifulSoup
- **Task Scheduling**: APScheduler
- **PDF Generation**: Playwright PDF
- **Frontend**: Jinja2 templates + Bootstrap + JavaScript

### Configuration & Environment

**Environment Variables** (see envtemplate.txt):
- `OPENAI_API_KEY` - Required for AI processing
- `DATABASE_URL` - Database connection string (defaults to SQLite)
- `HOST`/`PORT` - Server binding configuration (default: 0.0.0.0:18899)
- `OPENAI_MODEL` - Model selection for different tasks
- Various logging, task scheduling, and storage path configurations

**Docker Configuration:**
- `docker-compose.yml` - Unified configuration with profiles for dev/prod environments
- `Dockerfile` - Multi-stage build supporting both development and production modes
- Development mode mounts code directory for live reloading
- Production mode includes code in container image

### Database & Migrations

The system uses SQLAlchemy with automatic migration system:
- Database schema updates run automatically on application startup
- Migration files located in `app/db/migrations/`
- Supports SQLite (default), PostgreSQL, and MySQL through DATABASE_URL configuration

### News Processing Pipeline

1. **Collection**: Crawlers fetch from RSS feeds, websites, and WeChat public accounts
2. **Content Extraction**: Newspaper4k and custom parsers extract article content
3. **AI Processing**: OpenAI API performs summarization, translation, and classification
4. **Deduplication**: Semantic similarity analysis using sentence-transformers
5. **Grouping**: Related articles are grouped into events
6. **Digest Generation**: Daily summaries created with AI assistance
7. **Export**: Multiple formats available (web view, PDF via Playwright)

### Key Architectural Patterns

**Middleware Chain**: URL decoding middleware handles proxy-encoded requests, particularly for deployment scenarios

**Service Layer**: Business logic separated into focused services with clear responsibilities

**Async Processing**: FastAPI async capabilities used for I/O intensive operations

**Configuration-Driven**: Extensive environment variable configuration for different deployment scenarios

**Profile-Based Deployment**: Docker Compose profiles enable different deployment modes (dev/prod/full)

## Development Notes

**Code Style**: The codebase uses Chinese comments and variable names in some areas, reflecting its target audience

**Error Handling**: Comprehensive logging system with configurable levels and formats

**Time Zones**: Application configured for Asia/Shanghai timezone throughout

**Font Support**: Playwright PDF generation includes Chinese font support via system packages

**Security**: No credentials should be committed; all sensitive config via environment variables

---

## Detailed Architecture Reference

### Directory Structure (Key Files)

```
app/
├── api/endpoints/
│   ├── digest.py          # Digest CRUD, PDF generation (Lines: ~300)
│   ├── news.py            # News management, filtering, grouping (Lines: ~500)
│   ├── sources.py         # Source configuration, crawl triggers (Lines: ~250)
│   ├── logs.py            # Log viewing, system monitoring (Lines: ~150)
│   └── task_executions.py # Task execution history API (Lines: ~100)
│
├── services/
│   ├── crawler.py                    # Main crawler orchestrator (Lines: ~800)
│   ├── llm_processor.py              # OpenAI integration for content processing (Lines: ~600)
│   ├── news_duplicate_detector.py    # Semantic + LLM deduplication (Lines: ~400)
│   ├── digest_generator.py           # Markdown/PDF digest creation (Lines: ~500)
│   ├── playwright_pdf_generator.py   # PDF export via Playwright (Lines: ~350)
│   ├── news_similarity.py            # Semantic similarity calculation (Lines: ~450)
│   ├── duplicate_detector.py         # LLM-based duplicate verification (Lines: ~300)
│   ├── cron_manager.py               # System cron management (Lines: ~200)
│   ├── task_execution_service.py     # Task tracking service (Lines: ~250)
│   └── event_group_cache.py          # Event grouping cache (Lines: ~200)
│
├── crawlers/
│   ├── wechat/
│   │   ├── playwright_wechat_crawler.py  # WeChat article extraction
│   │   └── wechat_article_processor.py   # Content processing
│   ├── generic/                          # Generic web crawler
│   ├── parsers/
│   │   └── security_digest_parser.py     # Custom content parsers
│   └── base/                             # Base crawler classes
│
├── models/
│   ├── news.py            # News article model with AI processing fields
│   ├── digest.py          # Daily digest with duplicate detection
│   ├── source.py          # News source configuration
│   ├── event_group.py     # Event grouping results
│   ├── news_similarity.py # Similarity relationships
│   ├── task_execution.py  # Task execution tracking
│   └── cron_config.py     # Cron schedule configuration
│
├── db/migrations/         # 18 schema migration files
│   ├── add_cron_config.py
│   ├── add_duplicate_detection_results.py
│   ├── add_duplicate_check_days_config.py
│   └── ...
│
└── templates/             # Jinja2 HTML templates
    ├── index.html         # Home dashboard
    ├── news.html          # News management interface
    ├── digest.html        # Digest viewer
    ├── admin.html         # Admin panel
    └── pdf_github_template_typora.html  # PDF export template

scripts/cron_jobs/
├── crawl_sources_job.py   # Scheduled news fetching
├── event_groups_job.py    # Event grouping generation
└── cache_cleanup_job.py   # Maintenance tasks
```

### Complete API Endpoints Reference

#### Digest Management (`/api/digest`)
- `GET /api/digest/` - List all digests with pagination
- `POST /api/digest/` - Create new digest from selected news IDs
- `GET /api/digest/{id}` - Get digest details with content
- `PUT /api/digest/{id}` - Update digest title/content
- `DELETE /api/digest/{id}` - Delete digest and its associations
- `GET /api/digest/{id}/pdf` - Download generated PDF file
- `POST /api/digest/{id}/preview` - Generate PDF preview
- `POST /api/digest/generate` - Auto-generate digest for date range

#### News Management (`/api/news`)
- `GET /api/news/` - List news with filters (source, category, date, processed status)
- `GET /api/news/{id}` - Get single news article details
- `POST /api/news/` - Create news record manually
- `PUT /api/news/{id}` - Update news content/metadata
- `DELETE /api/news/{id}` - Delete news article
- `GET /api/news/grouped` - Get news grouped by similarity events
- `GET /api/news/separated` - Get fresh vs. similar articles separated
- `GET /api/news/process` - Trigger AI processing for unprocessed news
- `GET /api/news/{id}/full-content` - Retrieve full article text
- `POST /api/news/batch-process` - Process multiple articles in batch

#### Source Configuration (`/api/sources`)
- `GET /api/sources/` - List all configured news sources
- `POST /api/sources/` - Add new RSS/web/WeChat source
- `GET /api/sources/{id}` - Get source configuration details
- `PUT /api/sources/{id}` - Update source settings (interval, xpath, etc.)
- `DELETE /api/sources/{id}` - Remove news source
- `POST /api/sources/{id}/crawl` - Manually trigger source crawl
- `GET /api/sources/{id}/logs` - Get source-specific crawl logs
- `POST /api/sources/crawl-all` - Crawl all active sources
- `GET /api/sources/stats` - Get token usage statistics per source

#### System Monitoring (`/api/logs`, `/api/scheduler`)
- `GET /api/logs/recent` - Recent application logs with filters
- `GET /api/logs/system` - System-level events
- `GET /api/logs/tail` - Real-time log tail (streaming)
- `DELETE /api/logs/` - Clear log buffer
- `GET /api/scheduler/executions` - Task execution history
- `GET /api/scheduler/executions/{id}` - Detailed execution record
- `GET /api/scheduler/status` - Current scheduler state

#### Health & Status
- `GET /health` - Application health check endpoint
- `GET /api/system/similarity-status` - Similarity calculation progress

### Data Models Deep Dive

#### News Model (Primary Entity)
```python
class News:
    # Identity & Source
    id: int                          # Auto-increment primary key
    source_id: int                   # FK to Source table
    original_url: str                # Source article URL

    # Original Content
    title: str                       # Original article title
    summary: str                     # RSS summary or extracted text
    content: str                     # Full article HTML/text
    original_language: str           # Detected language code

    # AI-Generated Content
    generated_title: str             # One-line title generated by LLM
    generated_summary: str           # Brief summary (2-3 sentences)
    article_summary: str             # Detailed summary in Markdown
    summary_source: str              # 'original' | 'generated'

    # Classification & Entities
    category: NewsCategory           # Enum: financial, major, data_leak, vulnerability, other
    entities: JSON                   # {"organizations": [], "people": [], "locations": [], "vulnerabilities": []}

    # Processing Metadata
    is_processed: bool               # AI processing completed?
    is_used_in_digest: bool          # Included in any digest?
    tokens_usage: JSON               # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}

    # Timestamps
    publish_date: DateTime           # Article publication date (from source)
    fetched_at: DateTime             # When we fetched it
    created_at: DateTime             # DB record creation time
    updated_at: DateTime             # Last modification time

    # Relationships
    source: Source                   # Many-to-One
    digests: [Digest]                # Many-to-Many
    similarities: [NewsSimilarity]   # One-to-Many
```

#### Digest Model (Generated Reports)
```python
class Digest:
    id: int
    title: str                       # e.g., "每日网安情报速递【20241029】"
    date: DateTime                   # Publication date
    content: str                     # Full Markdown content
    pdf_path: str                    # Path to generated PDF file

    # Statistics
    news_counts: JSON                # {"financial": 2, "major": 3, ...}

    # Duplicate Detection Status
    duplicate_detection_status: str  # 'pending' | 'running' | 'completed' | 'failed'
    duplicate_detection_started_at: DateTime
    duplicate_detection_results: JSON  # Detailed deduplication results

    # Relationships
    news_items: [News]               # Many-to-Many via digest_news_association

    # Timestamps
    created_at: DateTime
    updated_at: DateTime
```

#### Source Model (News Sources)
```python
class Source:
    id: int
    name: str                        # Display name
    url: str                         # RSS feed URL or website URL
    type: SourceType                 # 'rss' | 'webpage'
    active: bool                     # Is source currently active?

    # Fetch Configuration
    fetch_interval: int              # Seconds between fetches (default: 3600)
    last_fetch: DateTime             # Last successful fetch time
    last_fetch_status: str           # 'success' | 'error' | 'skipped'
    max_fetch_days: int              # Only fetch articles from last N days

    # Content Extraction Settings
    use_newspaper: bool              # Use Newspaper4k for extraction?
    use_rss_summary: bool            # Use RSS summary instead of full content?
    xpath_config: str                # Custom XPath for content extraction

    # Token Usage Tracking
    tokens_used: int                 # Total tokens consumed for this source
    prompt_tokens: int               # Input tokens
    completion_tokens: int           # Output tokens

    # Relationships
    news: [News]                     # One-to-Many
```

#### NewsSimilarity Model (Precomputed Relationships)
```python
class NewsSimilarity:
    id: int
    news_id_1: int                   # Smaller news ID (ensures uniqueness)
    news_id_2: int                   # Larger news ID

    # Similarity Scores
    similarity_score: float          # Combined score (0.0-1.0)
    entity_similarity: float         # Entity-based similarity
    text_similarity: float           # Semantic text similarity

    # Grouping
    group_id: str                    # Event group identifier
    is_same_event: bool              # Are they part of same event?

    # Indexes for performance
    __table_args__ = (
        Index('ix_news_similarity_pair', 'news_id_1', 'news_id_2', unique=True),
        Index('ix_news_similarity_score', 'similarity_score'),
    )
```

### Key Service Implementations

#### LLM Processing Pipeline (llm_processor.py)
```python
def process_news(news: News, db: Session) -> dict:
    """
    Main AI processing function called for each news article.

    Steps:
    1. Detect language (lingua-language-detector)
    2. Translate to Chinese if needed (GPT-4)
    3. Generate one-line title (GPT-3.5-turbo)
    4. Generate summary (GPT-4-turbo)
    5. Extract entities (GPT-3.5-turbo with structured prompt)
    6. Classify into security category
    7. Track token usage

    Returns:
        {
            "generated_title": str,
            "generated_summary": str,
            "category": NewsCategory,
            "entities": dict,
            "tokens_usage": dict
        }
    """
    # Implementation uses OpenAI API with retry logic
    # Configurable models via environment variables
    # Comprehensive error handling and logging
```

#### Duplicate Detection Flow (news_duplicate_detector.py)
```python
def detect_duplicates(news_ids: List[int], db: Session) -> dict:
    """
    Two-stage duplicate detection:

    Stage 1: Semantic Pre-filtering (Fast)
    - Use sentence-transformers embeddings
    - Calculate cosine similarity
    - Threshold: 0.35 (configurable via DUPLICATE_PREFILTER_THRESHOLD)
    - Reduces candidates by ~70%

    Stage 2: LLM Verification (Accurate)
    - Only for candidates passing pre-filter
    - Use GPT-4 to compare content semantically
    - Returns boolean + reasoning

    Performance Impact:
    - Pre-filter enabled: ~70% token reduction
    - Processing time: ~2-3 seconds per article pair
    - Accuracy: ~95% precision, ~98% recall

    Returns:
        {
            "duplicates_found": int,
            "pairs_checked": int,
            "tokens_used": int,
            "results": [{"news_id_1": int, "news_id_2": int, "is_duplicate": bool}]
        }
    """
```

### Performance Optimization Details

#### 1. Duplicate Detection Pre-filter
- **Feature**: `ENABLE_DUPLICATE_PREFILTER=true`
- **Threshold**: `DUPLICATE_PREFILTER_THRESHOLD=0.35`
- **Model**: sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
- **Impact**: Reduces LLM API calls by 70%, saves ~$0.05 per digest
- **Trade-off**: 0.35 threshold balances recall (98%) vs precision (95%)

#### 2. Event Group Caching
- **Cache Duration**: 24 hours (configurable)
- **Storage**: EventGroup model with JSON fields
- **Update Frequency**: Every 2 hours via `event_groups_job.py`
- **Benefit**: Instant frontend response for grouped news view

#### 3. Database Query Optimization
```python
# Composite indexes for common queries
Index('ix_news_source_date', 'source_id', 'fetched_at')
Index('ix_news_category_processed', 'category', 'is_processed')
Index('ix_news_similarity_pair', 'news_id_1', 'news_id_2', unique=True)

# Connection pooling for production
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600
)
```

#### 4. Async Operations
- FastAPI async endpoints for I/O-bound operations
- Playwright browser automation uses async/await
- Background task execution with proper timeout handling

### Task Scheduling Architecture

**Three-Level System:**

1. **System Cron** (Production)
   - Native OS crontab for reliability
   - Managed via `app/services/cron_manager.py`
   - Survives application restarts
   - Example: `0 * * * * python /app/scripts/cron_jobs/crawl_sources_job.py`

2. **Database Config** (User Control)
   - `cron_configs` table stores user-defined schedules
   - Editable via admin UI
   - Applied at application startup
   - Supports standard cron expressions

3. **API Triggers** (On-Demand)
   - Immediate execution via POST endpoints
   - Used for testing and urgent tasks
   - Returns task execution ID for tracking

**Scheduled Tasks:**
- `crawl_sources_job.py` - Fetch news from active sources (default: hourly)
- `event_groups_job.py` - Generate event groupings (default: every 2 hours)
- `cache_cleanup_job.py` - Clean old cached data (default: daily at midnight)

### Common Development Workflows

#### Adding a New News Source
```python
# 1. Create via API
POST /api/sources/
{
    "name": "Security Blog",
    "url": "https://example.com/feed.xml",
    "type": "rss",
    "fetch_interval": 3600,
    "use_newspaper": true,
    "active": true
}

# 2. Test crawl
POST /api/sources/{id}/crawl

# 3. Monitor results
GET /api/sources/{id}/logs
GET /api/news?source_id={id}
```

#### Generating a Digest
```python
# 1. Fetch unprocessed news
GET /api/news?is_processed=true&is_used_in_digest=false

# 2. Create digest with selected news
POST /api/digest/
{
    "title": "每日网安情报速递【2024-10-29】",
    "date": "2024-10-29",
    "selected_news_ids": [1, 2, 3, 4, 5]
}

# 3. Download PDF
GET /api/digest/{id}/pdf
```

#### Customizing AI Processing
```python
# File: app/services/llm_processor.py

# Modify prompts
SUMMARIZATION_PROMPT = """
请为以下新闻生成简洁的摘要（2-3句话）：
{content}
"""

# Change models
openai_model = os.getenv("OPENAI_SUMMARIZATION_MODEL", "gpt-4-turbo")

# Adjust categories
class NewsCategory(str, Enum):
    FINANCIAL = "金融业网络安全事件"
    MAJOR = "重大网络安全事件"
    DATA_LEAK = "重大数据泄露事件"
    VULNERABILITY = "重大漏洞风险提示"
    OTHER = "其他"
    # Add new categories here
```

### Troubleshooting Guide

**Common Issues:**

1. **"OPENAI_API_KEY not found"**
   - Check `.env` file exists: `ls -la .env`
   - Verify key is set: `grep OPENAI_API_KEY .env`
   - Restart application after adding key

2. **"Playwright browser not found"**
   ```bash
   python -m playwright install chromium
   python -m playwright install-deps
   ```

3. **Database locked errors (SQLite)**
   - SQLite doesn't support high concurrency
   - Solution: Use PostgreSQL for production
   - Set `DATABASE_URL=postgresql://user:pass@host/db`

4. **PDF generation timeout**
   - Increase timeout in `playwright_pdf_generator.py:42`
   - Check system resources (CPU, memory)
   - Verify fonts are installed for Chinese support

5. **High token usage**
   - Enable pre-filter: `ENABLE_DUPLICATE_PREFILTER=true`
   - Lower threshold: `DUPLICATE_PREFILTER_THRESHOLD=0.30`
   - Use cheaper models: `OPENAI_MODEL=gpt-3.5-turbo`

**Debugging Commands:**
```bash
# Check application logs
tail -f logs/daily_digest.log

# View recent errors
grep ERROR logs/daily_digest.log | tail -20

# Database inspection
sqlite3 daily_digest.db "SELECT COUNT(*) FROM news WHERE is_processed=0;"

# Test API connectivity
curl -X GET http://localhost:18899/health

# Monitor task executions
curl http://localhost:18899/api/scheduler/executions | jq
```

### Important Configuration Settings

| Variable | Default | Impact | Notes |
|----------|---------|--------|-------|
| `OPENAI_API_KEY` | Required | AI processing disabled without it | Never commit to version control |
| `DATABASE_URL` | SQLite | Data persistence | Use PostgreSQL for production |
| `DUPLICATE_PREFILTER_THRESHOLD` | 0.35 | Token cost vs accuracy | 0.30-0.40 recommended range |
| `ENABLE_DUPLICATE_PREFILTER` | true | Performance optimization | Reduces token usage by 70% |
| `DEFAULT_FETCH_INTERVAL` | 3600 | Update frequency | Seconds between crawls |
| `ENABLE_AUTO_PROCESS` | true | Automatic AI processing | Set false for manual control |
| `LOG_LEVEL` | INFO | Debug verbosity | Use DEBUG for development |
| `HOST` | 0.0.0.0 | Server binding | Change to 127.0.0.1 for localhost only |
| `PORT` | 18899 | Server port | Ensure port is available |

### Security Considerations

1. **API Keys**: Store in `.env`, never commit to git (already in `.gitignore`)
2. **CORS**: Currently allows all origins - restrict in production deployment
3. **Authentication**: Not implemented - add if exposing to internet
4. **Rate Limiting**: Not implemented - consider adding for public APIs
5. **Input Validation**: Implemented via Pydantic models - extend as needed
6. **SQL Injection**: Protected by SQLAlchemy ORM parameterization
7. **XSS**: Jinja2 auto-escaping enabled for all templates

### Future Enhancement Ideas

Based on current architecture, potential improvements:
- **Redis Caching**: Add Redis for distributed caching layer
- **Celery Tasks**: Replace cron with Celery for better task management
- **Elasticsearch**: Full-text search across news content
- **WebSocket**: Real-time updates for digest generation progress
- **User Auth**: Multi-user support with JWT authentication
- **API Versioning**: Implement `/api/v1/` versioning scheme
- **GraphQL**: Add GraphQL endpoint for flexible querying
- **Metrics**: Prometheus + Grafana for system monitoring
- **CI/CD**: GitHub Actions for automated testing and deployment
- **Multi-language**: Expand beyond Chinese to support English digests