# People Discovery Agent

An API-first deep person intelligence engine that searches 16+ sources, runs a multi-step LangGraph agent pipeline, and builds comprehensive person profiles — complete with career timelines, sentiment analysis, influence scoring, and meeting preparation.

**Live deployments**
- Frontend: [https://frontend-theta-seven-44.vercel.app](https://frontend-theta-seven-44.vercel.app)
- Backend API: [https://people-discovery-agent-production.up.railway.app](https://people-discovery-agent-production.up.railway.app)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Features](#features)
3. [Tech Stack](#tech-stack)
4. [Agent Pipeline](#agent-pipeline)
5. [Data Sources](#data-sources)
6. [Quick Start](#quick-start)
7. [Environment Variables](#environment-variables)
8. [API Reference](#api-reference)
9. [LLM Strategy](#llm-strategy)
10. [Caching Strategy](#caching-strategy)
11. [Database Schema](#database-schema)

---

## Architecture Overview

```
Browser / API Client
        │
        ▼
  Next.js (Vercel)          ← frontend
  /api/* rewrites           ← server-side proxy (no CORS in browser)
        │
        ▼
  FastAPI (Railway)         ← backend
  ├── Auth (JWT)
  ├── Rate Limiting
  ├── 4 API Routers
  └── LangGraph Agent
        │
        ├── Tavily / SerpAPI / Apify / Firecrawl / GitHub / SociaVault
        ├── SQLite / PostgreSQL (results + cache)
        └── OpenAI / DeepSeek / Anthropic (LLMs)
```

- **Frontend** (Next.js 14, Vercel): All `/api/*` calls are proxied server-side to the Railway backend via `next.config.js` rewrites, so no CORS issues in the browser.
- **Backend** (FastAPI, Railway): Runs the LangGraph discovery agent, stores results in SQLite/PostgreSQL, and exposes a REST API.
- **Agent** (LangGraph): A 6-node linear pipeline that plans searches, executes them in parallel across 16 tools, analyzes/enriches/scores the results, and synthesizes a final profile.

---

## Features

### Public API Demo Page
- Structured discovery form: name, company, role, location, LinkedIn URL, Twitter handle, GitHub username, Instagram handle, free-text context
- Live curl command generator that mirrors the form input
- Real-time job polling with progress indicator
- Full person profile display with tabbed source viewer

### Admin Dashboard (JWT-authenticated)
- **Persons list** — search, filter, paginate all discovered persons
- **Person detail** — full profile with tabbed source viewer, version history, confidence and reputation scores
- **Edit profile** — update name, role, company, location, bio inline
- **Re-search** — re-run the full agent pipeline for any existing person
- **Export** — download any profile as JSON, CSV, or styled PDF
- **Batch discovery** — upload a list of persons and queue all jobs at once
- **Compare persons** — side-by-side comparison of two profiles with relationship mapping
- **Cost dashboard** — total spend, job count, average cost, per-job breakdown
- **API key management** — create/revoke API keys with per-day rate limits
- **Webhook management** — register endpoints, view delivery history, HMAC-signed payloads
- **API documentation** — built-in reference of all endpoints

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, React 18, Tailwind CSS |
| Backend | FastAPI, LangGraph, SQLAlchemy 2.0 |
| Database | SQLite + aiosqlite (default) / PostgreSQL + asyncpg (production) |
| LLMs | GPT-4.1 Mini (plan/analyze/sentiment), DeepSeek V3 / Claude (synthesis) |
| Search tools | Tavily, Apify, SerpAPI, Firecrawl, GitHub API, SociaVault |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Deployment | Railway (backend), Vercel (frontend) |

---

## Agent Pipeline

Every discovery job runs this 6-node LangGraph pipeline synchronously:

```
plan_searches
      │
execute_searches      ← parallel across all 16 tools + Firecrawl deep extract
      │
analyze_results       ← LLM disambiguation, identity confirmation, confidence score
      │
enrich_data           ← career timeline, fact dedup, source diversity (pure Python)
      │
analyze_sentiment     ← LLM per-source sentiment, reputation score 0–100
      │
synthesize_profile    ← LLM final bio (400–600 words), key facts, career timeline, sources
```

| Node | Model | Purpose |
|------|-------|---------|
| `plan_searches` | GPT-4.1 Mini | Generate 8–10 targeted queries covering all source types |
| `execute_searches` | — | Run all queries in parallel; gap-fill skipped platforms; dedup by URL |
| `analyze_results` | GPT-4.1 Mini | Disambiguate identity, extract facts, assign confidence score |
| `enrich_data` | Pure Python | Build chronological career timeline, dedup facts, compute source diversity |
| `analyze_sentiment` | GPT-4.1 Mini | Score per-source sentiment; produce overall reputation score |
| `synthesize_profile` | DeepSeek V3 (fallback: Claude / GPT-4.1 Mini) | Generate final polished profile |

After the pipeline completes, results are merged into the database (existing person record is updated or a new one is created), webhooks are fired, and the job is marked `completed`.

---

## Data Sources

| # | Source | Tool | Cost |
|---|--------|------|------|
| 1 | Web Search | Tavily API | $0.016/query |
| 2 | News | Tavily (news mode) | $0.016/query |
| 3 | Academic Papers | Tavily + SerpAPI Scholar | $0.026/query |
| 4 | LinkedIn Profile | Apify DataWeave | $0.002/profile |
| 5 | LinkedIn Posts | Apify Posts Scraper | $0.0035/post |
| 6 | Twitter / X | Apify Scraper | $0.0004/tweet |
| 7 | YouTube | youtube-transcript-api | Free |
| 8 | GitHub | GitHub REST API | Free (token recommended) |
| 9 | Reddit | Apify Scraper | $0.003/result |
| 10 | Medium | Apify Scraper | $0.002/article |
| 11 | Google Scholar | SerpAPI | $0.01/lookup |
| 12 | Instagram | SociaVault API | $0.005/profile |
| 13 | Google News | SerpAPI | $0.01/query |
| 14 | Crunchbase | SerpAPI | $0.01/query |
| 15 | Patents | SerpAPI | $0.01/query |
| 16 | StackOverflow | SerpAPI | $0.01/query |
| + | Deep page extract | Firecrawl | $0.001–0.003/page |

**Average cost per discovery:** ~$0.05–$0.25 first run, ~$0.01 on cache hit.

All optional sources (Apify, SerpAPI, Firecrawl, SociaVault, GitHub) degrade gracefully if the API key is not set — the agent skips those sources and continues with the rest.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY and TAVILY_API_KEY
uvicorn app.main:app --reload --port 8000
```

The backend creates a local `discovery.db` (SQLite) on first run. Visit [http://localhost:8000/docs](http://localhost:8000/docs) for the auto-generated Swagger UI.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
# BACKEND_URL defaults to http://localhost:8000 — no change needed for local dev
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Admin login defaults: `admin@discovery.local` / `changeme123`.

### Docker (both services)

```bash
docker-compose up --build
```

---

## Environment Variables

### Backend (`backend/.env`)

```bash
# ── Required ──────────────────────────────────────────────
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...

# ── Search sources (optional, degrade gracefully if absent) ──
APIFY_API_KEY=apify_api_...
FIRECRAWL_API_KEY=fc-...
SERPAPI_API_KEY=...
SOCIAVAULT_API_KEY=...
GITHUB_TOKEN=ghp_...
YOUTUBE_API_KEY=...

# ── Synthesis LLM (pick one or leave blank for GPT-4.1 Mini) ──
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
ANTHROPIC_API_KEY=sk-ant-...

# ── Planning LLM (alternative providers, OpenAI-compatible) ──
GROQ_API_KEY=gsk_...
TOGETHER_API_KEY=...
PLANNING_BASE_URL=          # e.g. https://api.groq.com/openai/v1

# ── Model selection ──
PLANNING_MODEL=gpt-4.1-mini
SYNTHESIS_MODEL=deepseek-chat   # or: claude-3-5-sonnet-20241022, gpt-4.1-mini

# ── Database ──
DATABASE_URL=sqlite+aiosqlite:///./discovery.db
# Production: DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/discovery

# ── Admin credentials ──
ADMIN_EMAIL=admin@discovery.local
ADMIN_PASSWORD=changeme123
JWT_SECRET_KEY=your-secure-random-secret-here

# ── CORS ──
CORS_ORIGINS=http://localhost:3000,https://your-app.vercel.app
CORS_ALLOW_REGEX=https://your-app.*\.vercel\.app

# ── Guardrails ──
MAX_CONCURRENT_JOBS=5
MAX_DAILY_DISCOVERIES=100

# ── Observability ──
LOG_LEVEL=INFO
SENTRY_DSN=
ENVIRONMENT=development
REDIS_URL=          # Optional — for distributed rate limiting
```

### Frontend (`frontend/.env.local`)

```bash
# URL of the backend — used by Next.js server-side proxy (not exposed to browser)
BACKEND_URL=http://localhost:8000
# Production (set in Vercel dashboard):
# BACKEND_URL=https://people-discovery-agent-production.up.railway.app
```

---

## API Reference

All endpoints are prefixed with `/api`. The frontend proxies all `/api/*` requests to the backend, so from the browser you can also call `https://frontend-theta-seven-44.vercel.app/api/*`.

**Authentication** — most write endpoints and admin endpoints require a JWT Bearer token:
```
Authorization: Bearer <access_token>
```

---

### Health

#### `GET /api/health`
Returns backend health and database status. No auth required.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/health
```

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": 1741612345.6,
  "database": "ok"
}
```

---

### Authentication

#### `POST /api/auth/login`
Exchange admin credentials for a JWT access + refresh token pair.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@discovery.local", "password": "changeme123"}'
```

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "email": "admin@discovery.local",
  "role": "admin"
}
```

#### `POST /api/auth/refresh`
Exchange a refresh token for a new token pair.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

---

### Discovery

#### `POST /api/discover`
Start a single person discovery job. Returns a `job_id` to poll.  
**Auth required.**

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/discover \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Prashant Parashar",
    "company": "Delhivery",
    "role": "CTO",
    "location": "Gurugram, India",
    "linkedin_url": "",
    "twitter_handle": "",
    "github_username": "",
    "instagram_handle": "",
    "context": "Previously worked at Ola and Zomato"
  }'
```

**All fields except `name` are optional.**

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "running",
  "message": "Discovery started. Poll GET /api/jobs/{job_id} for status."
}
```

**Rate limits:** Max `MAX_CONCURRENT_JOBS` (default 5) running at once. Max `MAX_DAILY_DISCOVERIES` (default 100) per day. Returns `429` if exceeded.

---

#### `POST /api/discover/batch`
Start discovery for up to 20 people in one call. Returns a list of job IDs.  
**Auth required.**

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/discover/batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "persons": [
      {"name": "Sam Altman", "company": "OpenAI"},
      {"name": "Jensen Huang", "company": "NVIDIA"},
      {"name": "Sundar Pichai", "company": "Google"}
    ]
  }'
```

```json
{
  "jobs": [
    {"job_id": "uuid-1", "name": "Sam Altman", "status": "running"},
    {"job_id": "uuid-2", "name": "Jensen Huang", "status": "running"},
    {"job_id": "uuid-3", "name": "Sundar Pichai", "status": "running"}
  ],
  "total": 3
}
```

---

### Jobs

#### `GET /api/jobs/{job_id}`
Poll a discovery job. Returns `status: running` while in progress, `completed` or `failed` when done.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6 \
  -H "Authorization: Bearer <token>"
```

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed",
  "person_id": "a1b2c3d4-...",
  "input_params": {"name": "Prashant Parashar", "company": "Delhivery", "...": "..."},
  "total_cost": 0.042,
  "latency_ms": 38450,
  "sources_hit": 14,
  "cache_hits": 2,
  "cost_breakdown": {
    "plan_searches": 0.001,
    "analyze_results": 0.008,
    "analyze_sentiment": 0.005,
    "synthesize_profile": 0.028
  },
  "created_at": "2026-03-12T10:00:00Z",
  "completed_at": "2026-03-12T10:00:38Z"
}
```

---

### Persons

#### `GET /api/persons`
List all discovered persons with pagination and search.

Query parameters:
- `skip` — offset (default 0)
- `limit` — page size (default 20, max 100)
- `search` — filter by name or company

```bash
curl "https://people-discovery-agent-production.up.railway.app/api/persons?search=Prashant&limit=10" \
  -H "Authorization: Bearer <token>"
```

```json
{
  "total": 1,
  "persons": [
    {
      "id": "a1b2c3d4-...",
      "name": "Prashant Parashar",
      "company": "Delhivery",
      "current_role": "CTO",
      "confidence_score": 0.91,
      "status": "discovered",
      "sources_count": 14,
      "created_at": "2026-03-12T10:00:38Z",
      "updated_at": "2026-03-12T10:00:38Z"
    }
  ]
}
```

---

#### `GET /api/persons/{id}`
Get the full person profile including all sources and job history.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-... \
  -H "Authorization: Bearer <token>"
```

```json
{
  "id": "a1b2c3d4-...",
  "name": "Prashant Parashar",
  "current_role": "CTO",
  "company": "Delhivery",
  "location": "Gurugram, India",
  "bio": "Prashant Parashar is a senior technology executive...",
  "confidence_score": 0.91,
  "reputation_score": 0.78,
  "status": "discovered",
  "version": 1,
  "education": [{"degree": "B.Tech", "institution": "IIT", "year": "2005"}],
  "key_facts": ["Led tech at Ola", "Built Delhivery's logistics platform"],
  "expertise": ["Distributed Systems", "Logistics Tech", "Engineering Leadership"],
  "career_timeline": [
    {"period": "2020–present", "role": "CTO", "company": "Delhivery"},
    {"period": "2016–2020", "role": "VP Engineering", "company": "Ola"},
    {"period": "2013–2016", "role": "Senior Engineer", "company": "Zomato"}
  ],
  "notable_work": ["Built Delhivery's real-time tracking system"],
  "social_links": {
    "linkedin": "https://linkedin.com/in/prashant-parashar",
    "github": "https://github.com/prashantparashar",
    "twitter": "https://twitter.com/prashant"
  },
  "sources": [
    {
      "id": "src-uuid",
      "source_type": "linkedin",
      "platform": "linkedin",
      "url": "https://linkedin.com/in/prashant-parashar",
      "title": "Prashant Parashar - CTO at Delhivery",
      "confidence": 0.95,
      "relevance_score": 0.95,
      "source_reliability": 0.9,
      "fetched_at": "2026-03-12T10:00:15Z"
    }
  ],
  "jobs": [
    {
      "id": "job-uuid",
      "status": "completed",
      "total_cost": 0.042,
      "latency_ms": 38450,
      "sources_hit": 14,
      "cache_hits": 2,
      "created_at": "2026-03-12T10:00:00Z",
      "completed_at": "2026-03-12T10:00:38Z"
    }
  ],
  "created_at": "2026-03-12T10:00:38Z",
  "updated_at": "2026-03-12T10:00:38Z"
}
```

---

#### `PUT /api/persons/{id}`
Update editable fields on a person profile.  
**Auth required.**

```bash
curl -X PUT https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-... \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "current_role": "Group CTO",
    "company": "Delhivery",
    "bio": "Updated bio text here..."
  }'
```

Updatable fields: `name`, `current_role`, `company`, `location`, `bio`.

---

#### `DELETE /api/persons/{id}`
Permanently delete a person and all associated sources, versions, and jobs.  
**Auth required.**

```bash
curl -X DELETE https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-... \
  -H "Authorization: Bearer <token>"
```

```json
{"deleted": true}
```

---

#### `GET /api/persons/{id}/export`
Export a person profile. `format` query param: `json` (default), `csv`, or `pdf`.

```bash
# JSON
curl "https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../export?format=json" \
  -H "Authorization: Bearer <token>" -o profile.json

# CSV
curl "https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../export?format=csv" \
  -H "Authorization: Bearer <token>" -o profile.csv

# PDF (styled report)
curl "https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../export?format=pdf" \
  -H "Authorization: Bearer <token>" -o profile.pdf
```

---

#### `POST /api/persons/{id}/re-search`
Re-run the full discovery pipeline using the person's existing data as input context.  
**Auth required.** Returns a new `job_id`.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../re-search \
  -H "Authorization: Bearer <token>"
```

```json
{"job_id": "new-uuid", "status": "running", "message": "Re-search started."}
```

---

### Intelligence Endpoints

These endpoints perform on-demand AI analysis on an already-discovered person using the stored sources. They use GPT-4.1 Mini and return structured JSON.  
**All require auth.**

#### `GET /api/persons/{id}/sentiment`
Analyze public sentiment across all sources.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../sentiment \
  -H "Authorization: Bearer <token>"
```

```json
{
  "overall_sentiment": "positive",
  "sentiment_score": 0.82,
  "source_sentiments": [
    {"source": "LinkedIn", "sentiment": "positive", "key_phrases": ["visionary leader", "top talent"]}
  ],
  "public_perception": "Widely regarded as a strong technical leader...",
  "controversy_flags": [],
  "strengths_in_perception": ["Technical depth", "Execution track record"],
  "risks": []
}
```

#### `GET /api/persons/{id}/influence`
Calculate a multi-dimensional influence score.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../influence \
  -H "Authorization: Bearer <token>"
```

```json
{
  "overall_influence_score": 74,
  "dimensions": {
    "thought_leadership": 80,
    "network_reach": 70,
    "media_presence": 65,
    "industry_impact": 85,
    "digital_footprint": 60
  },
  "key_influence_areas": ["Logistics tech", "Engineering leadership"],
  "comparable_profiles": ["other executives at similar scale"]
}
```

#### `POST /api/persons/relationships`
Map the relationship between two persons.  
**Auth required.**

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/relationships \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"person_a_id": "uuid-A", "person_b_id": "uuid-B"}'
```

```json
{
  "relationship_type": "professional",
  "connection_strength": "moderate",
  "shared_contexts": ["startup ecosystem", "e-commerce tech"],
  "potential_connection_points": ["Both led engineering at scale"],
  "relationship_summary": "Both are senior technology leaders in Indian tech..."
}
```

#### `POST /api/persons/{id}/meeting-prep`
Generate AI-powered meeting preparation notes.  
**Auth required.**

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../meeting-prep \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"context": "Partnership discussion for logistics software integration"}'
```

```json
{
  "executive_summary": "Senior tech executive with deep logistics and startup background...",
  "key_talking_points": ["Their experience scaling Delhivery's platform", "Open-source contributions"],
  "potential_interests": ["Engineering challenges at scale", "Supply chain automation"],
  "background_insights": ["Former IIT background", "Built teams of 500+ engineers"],
  "conversation_starters": ["What was the hardest scaling challenge at Delhivery?"],
  "areas_to_avoid": [],
  "recommended_approach": "Lead with technical depth; they respond well to engineering specifics."
}
```

#### `GET /api/persons/{id}/verify`
Cross-reference facts from all sources and flag inconsistencies.  
**Auth required.**

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/a1b2c3d4-.../verify \
  -H "Authorization: Bearer <token>"
```

```json
{
  "verified_facts": ["CTO at Delhivery confirmed across 4 sources"],
  "inconsistencies": [],
  "confidence_adjustments": [],
  "data_gaps": ["Education details sparse"],
  "verification_summary": "High confidence profile — key facts confirmed across multiple independent sources."
}
```

---

### Suggestions / Typeahead

#### `GET /api/suggest`
Typeahead for person names or company names. No auth required.

Query parameters:
- `q` — search prefix (min 1 char, required)
- `type` — `person` (default) or `company`
- `limit` — 1–20 (default 5)

```bash
# Person suggestions
curl "https://people-discovery-agent-production.up.railway.app/api/suggest?q=Prash&type=person"
```

```json
[
  {"id": "a1b2c3d4-...", "name": "Prashant Parashar", "company": "Delhivery"}
]
```

```bash
# Company suggestions
curl "https://people-discovery-agent-production.up.railway.app/api/suggest?q=Delh&type=company"
```

```json
[{"company": "Delhivery"}]
```

---

### Admin

#### `GET /api/admin/costs`
Cost dashboard statistics across all discovery jobs.  
**Auth required.**

```bash
curl https://people-discovery-agent-production.up.railway.app/api/admin/costs \
  -H "Authorization: Bearer <token>"
```

```json
{
  "total_spend": 1.2345,
  "total_jobs": 42,
  "average_cost": 0.0294,
  "recent_jobs": [
    {
      "id": "uuid",
      "total_cost": 0.042,
      "latency_ms": 38450,
      "sources_hit": 14,
      "cache_hits": 2,
      "created_at": "2026-03-12T10:00:38Z"
    }
  ]
}
```

#### `POST /api/cache/cleanup`
Purge all expired cache entries.  
**Auth required.**

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/cache/cleanup \
  -H "Authorization: Bearer <token>"
```

```json
{"cleaned": 47}
```

---

### API Keys

All API key endpoints require admin auth.

#### `GET /api/api-keys`
List all API keys with usage stats.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/api-keys \
  -H "Authorization: Bearer <token>"
```

```json
[
  {
    "id": "key-uuid",
    "name": "Production Integration",
    "rate_limit_per_day": 1000,
    "active": true,
    "usage_count": 127,
    "total_cost": 3.21,
    "last_used_at": "2026-03-12T09:55:00Z",
    "created_at": "2026-03-01T00:00:00Z"
  }
]
```

#### `POST /api/api-keys`
Create a new API key. The raw key is only returned once — store it immediately.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/api-keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "Production Integration", "rate_limit_per_day": 1000}'
```

```json
{
  "id": "key-uuid",
  "name": "Production Integration",
  "key": "dk_abc123...",
  "rate_limit_per_day": 1000,
  "active": true,
  "created_at": "2026-03-12T10:00:00Z"
}
```

#### `DELETE /api/api-keys/{key_id}`
Revoke an API key.

```bash
curl -X DELETE https://people-discovery-agent-production.up.railway.app/api/api-keys/key-uuid \
  -H "Authorization: Bearer <token>"
```

```json
{"revoked": true}
```

---

### Webhooks

All webhook endpoints require admin auth. Webhooks are fired after every completed discovery job (`job.completed` event).

#### `GET /api/webhooks`
List active webhook endpoints.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/webhooks \
  -H "Authorization: Bearer <token>"
```

```json
[
  {
    "id": "wh-uuid",
    "url": "https://your-server.com/hooks/discovery",
    "events": ["job.completed"],
    "active": true,
    "created_at": "2026-03-01T00:00:00Z"
  }
]
```

#### `POST /api/webhooks`
Register a new webhook endpoint.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "url": "https://your-server.com/hooks/discovery",
    "secret": "your-webhook-secret",
    "events": ["job.completed"]
  }'
```

Payloads are HMAC-SHA256 signed. Verify using the `X-Webhook-Signature` header:
```
X-Webhook-Signature: t=<timestamp>,v1=<hex_signature>
```

Payload structure:
```json
{
  "event": "job.completed",
  "data": {
    "job_id": "uuid",
    "person_id": "uuid",
    "status": "completed",
    "total_cost": 0.042,
    "sources_hit": 14
  }
}
```

#### `DELETE /api/webhooks/{webhook_id}`
Deactivate a webhook endpoint.

```bash
curl -X DELETE https://people-discovery-agent-production.up.railway.app/api/webhooks/wh-uuid \
  -H "Authorization: Bearer <token>"
```

```json
{"deactivated": true}
```

#### `GET /api/webhooks/{webhook_id}/deliveries`
View the last 50 delivery attempts for a webhook.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/webhooks/wh-uuid/deliveries \
  -H "Authorization: Bearer <token>"
```

```json
[
  {
    "id": "del-uuid",
    "event": "job.completed",
    "status_code": 200,
    "success": true,
    "attempts": 1,
    "created_at": "2026-03-12T10:00:45Z"
  }
]
```

---

## LLM Strategy

| Stage | Model | Approx. Cost (per 1M tokens) |
|-------|-------|------------------------------|
| Planner | `gpt-4.1-mini` | $0.40 in / $1.60 out |
| Analyzer | `gpt-4.1-mini` | $0.40 in / $1.60 out |
| Sentiment | `gpt-4.1-mini` | $0.40 in / $1.60 out |
| Synthesizer (default) | `deepseek-chat` (DeepSeek V3) | $0.14 in / $0.28 out |
| Synthesizer (alt 1) | `claude-3-5-sonnet-20241022` | $3.00 in / $15.00 out |
| Synthesizer (alt 2) | `gpt-4.1-mini` | $0.40 in / $1.60 out |

The synthesizer picks the active model in this priority: DeepSeek → Claude → GPT-4.1 Mini, based on which API keys are configured. The planner supports Groq or Together AI as drop-in alternatives via `PLANNING_BASE_URL`.

---

## Caching Strategy

Search results are cached in the database using a SHA-256 hash of `(query, search_type)` as the key. Cache hits skip the external API call entirely, reducing both cost and latency.

| Source | Cache TTL |
|--------|-----------|
| LinkedIn | 7 days |
| YouTube | 30 days |
| GitHub | 7 days |
| Google Scholar | 30 days |
| Twitter | 1 day |
| Reddit | 1 day |
| Web / News | 24 hours |
| All others | 24 hours |

---

## Database Schema

10 tables managed via SQLAlchemy async ORM:

| Table | Purpose |
|-------|---------|
| `persons` | Core person profiles (bio, career, social links, scores) |
| `person_sources` | Individual source results (URL, content, confidence) |
| `person_versions` | Snapshot history of profile changes |
| `discovery_jobs` | Job tracking (status, cost, latency, cache hits) |
| `api_keys` | Hashed API keys with rate limits and usage |
| `api_usage_logs` | Per-request usage log keyed to API key |
| `admin_users` | Admin accounts (hashed passwords) |
| `webhook_endpoints` | Registered webhook URLs with event filters |
| `webhook_deliveries` | Delivery attempt log (status, retries) |
| `search_cache` | Cached search results keyed by `(query_hash, source_type)` |

---

## License

MIT
