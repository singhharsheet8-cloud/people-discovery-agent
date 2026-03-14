# People Discovery Agent

An API-first deep person intelligence engine that searches 16+ sources, runs a multi-step LangGraph agent pipeline, and builds comprehensive profiles — with career timelines, sentiment analysis, influence scoring, CRM integration, Slack bot, public sharing, and meeting preparation.

**Live deployments**
- Frontend: [https://frontend-theta-seven-44.vercel.app](https://frontend-theta-seven-44.vercel.app)
- Backend API: [https://people-discovery-agent-production.up.railway.app](https://people-discovery-agent-production.up.railway.app)
- Swagger UI: [https://people-discovery-agent-production.up.railway.app/docs](https://people-discovery-agent-production.up.railway.app/docs)

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
  Next.js (Vercel)                  ← frontend
  /api/* server-side rewrites       ← no browser CORS issues
        │
        ▼
  FastAPI (Railway)                 ← backend
  ├── JWT Auth + API Key Auth + Rate Limiting
  ├── 6 API Routers
  │   ├── routes      (discover, persons, jobs, intelligence, admin)
  │   ├── api_keys    (API key management)
  │   ├── webhooks    (webhook endpoints)
  │   ├── suggest     (typeahead)
  │   ├── lists_notes (lists, notes, tags, audit, public share, analytics)
  │   └── integrations (HubSpot, Salesforce, Slack)
  └── LangGraph Agent
        │
        ├── 16 Search Tools (Tavily / SerpAPI / Apify / Firecrawl / GitHub / SociaVault)
        ├── PostgreSQL (Supabase) / SQLite (local dev)
        └── Groq (llama-3.1-8b · llama-4-scout · gpt-oss-20b) — 100% inference on Groq
```

---

## Features

### Public Demo Page (`/`)
- Discovery form: name, company, role, location, LinkedIn URL, Twitter, GitHub, Instagram, context
- Live curl command generator
- Real-time job polling with progress indicator
- Full profile display with tabbed source viewer

### Admin Dashboard (`/admin`) — JWT-authenticated

| Feature | Description |
|---------|-------------|
| Persons list | Search, filter, paginate all discovered persons |
| Person detail | Profile with tabbed source viewer, version history |
| Edit profile | Update name, role, company, location, bio inline |
| Re-search | Re-run full agent pipeline for an existing person |
| Export | Download as JSON, CSV, PDF (styled report), or PPTX (3-slide deck) |
| Batch discovery | Queue up to 20 persons at once |
| Compare persons | Side-by-side comparison + relationship mapping |
| Saved lists | Group persons into color-coded lists (e.g. "Prospects", "Speakers") |
| Notes | Attach private notes to any person |
| Tags | Tag persons for filtering and categorisation |
| Public share links | Generate a token-based public URL for any profile |
| Cost dashboard | Total spend, job count, average cost, per-job breakdown |
| Analytics dashboard | Aggregated stats, top companies, source distribution |
| Audit log | Full action history with user, IP, timestamp |
| API key management | Create/revoke keys with per-day rate limits |
| Webhook management | Register endpoints, view delivery history, HMAC signing |
| Admin user management | Create, list, delete admin/viewer/api_only users |
| Rate limits | Per-source API rate limit status |

### Public Profile Page (`/profile/[token]`)
Shareable, auth-free page showing bio, expertise, career timeline, education, social links, sources.

### Slack Bot
Use `/discover <name>` in any Slack channel to trigger discovery. Results posted back as Block Kit cards.

### CRM Integrations
One-click push of any discovered person to HubSpot (contact) or Salesforce (lead).

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 14, React 18, Tailwind CSS |
| Backend | FastAPI, LangGraph, SQLAlchemy 2.0 |
| Database | PostgreSQL via Supabase (production) / SQLite + aiosqlite (local dev) |
| LLMs | **All on Groq** — `llama-3.1-8b-instant` (plan/score), `llama-4-scout-17b` (analyze/disambiguate), `gpt-oss-20b` (synthesize) |
| Inference provider | [Groq](https://groq.com) — 560–1000 TPS, 83% cheaper than OpenAI gpt-4.1-mini |
| Search tools | Tavily, Apify, SerpAPI, Firecrawl, GitHub API, SociaVault |
| Image storage | Supabase Storage (permanent profile image hosting) |
| Auth | JWT (python-jose), bcrypt (passlib), API key headers |
| Deployment | Railway (backend), Vercel (frontend) |

---

## Agent Pipeline

```
plan_searches → execute_searches → analyze_results → enrich_data → analyze_sentiment → synthesize_profile
```

| Node | Model (Groq) | Purpose |
|------|-------------|---------|
| plan_searches | `llama-3.1-8b-instant` | Generate 8-10 diverse, deduplicated queries across all source types; post-processing guarantees web+news coverage |
| execute_searches | — | Parallel execution across 16 tools; gap-fills skipped platforms; deep-extracts top pages via Firecrawl |
| source_scorer | `llama-3.1-8b-instant` | LLM-powered per-source confidence scoring — relevance, reliability, corroboration; correctly detects namesakes |
| analyze_results | `llama-4-scout-17b-16e` | Disambiguate identity (100% P/R on namesake detection), extract facts, blend confidence score |
| enrich_data | Pure Python | Chronological career timeline, fact dedup, source diversity |
| analyze_sentiment | `gpt-4.1-mini` (OpenAI) | Per-source sentiment, overall reputation score |
| synthesize_profile | `openai/gpt-oss-20b` (Groq) | Final bio (400-600 words), key facts, career timeline, source ratings |

**Typical latency:** 60-120 seconds end-to-end (network + search tools dominate). LLM stages add ~3.2s total.  
After completion: results merged into DB, profile image resolved and stored in Supabase Storage, webhooks fired (`job.completed` or `person.updated`).

---

## Data Sources

| # | Source | Tool | Cost |
|---|--------|------|------|
| 1 | Web Search | Tavily API | $0.016/query |
| 2 | News | Tavily (news mode) | $0.016/query |
| 3 | Academic Papers | Tavily + SerpAPI Scholar | $0.026/query |
| 4 | LinkedIn Profile | Apify | $0.002/profile |
| 5 | LinkedIn Posts | Apify | $0.0035/post |
| 6 | Twitter / X | Apify | $0.0004/tweet |
| 7 | YouTube | youtube-transcript-api | Free |
| 8 | GitHub | GitHub REST API | Free (token recommended) |
| 9 | Reddit | Apify | $0.003/result |
| 10 | Medium | Apify | $0.002/article |
| 11 | Google Scholar | SerpAPI | $0.01/lookup |
| 12 | Instagram | SociaVault API | $0.005/profile |
| 13 | Google News | SerpAPI | $0.01/query |
| 14 | Crunchbase | SerpAPI | $0.01/query |
| 15 | Patents | SerpAPI | $0.01/query |
| 16 | StackOverflow | SerpAPI | $0.01/query |
| + | Deep page extract | Firecrawl | $0.001-0.003/page |

**Average cost:** ~$0.005-0.02 per discovery (with cache hits) · ~$0.03-0.15 first run  
LLM cost alone: ~$0.0013 per discovery (all on Groq — 83% cheaper than equivalent OpenAI pipeline)

---

## Quick Start

### Prerequisites
Python 3.11+ and Node.js 18+

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # edit with your API keys
uvicorn app.main:app --reload --port 8000
```

SQLite database `discovery.db` is created automatically. Swagger UI at http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local      # BACKEND_URL defaults to http://localhost:8000
npm run dev
```

Open http://localhost:3000. Default admin: `admin@discovery.local` / `changeme123`

### Docker

```bash
docker-compose up --build
```

---

## Environment Variables

### Backend (`backend/.env`)

```env
# ── LLM: Groq (primary inference provider for all 3 tiers) ────────────────────
GROQ_API_KEY=gsk_...          # Required — used for all three LLM tiers

# ── LLM Tier 1: Planning & Source Scoring ─────────────────────────────────────
# Model: llama-3.1-8b-instant  |  560 TPS  |  $0.05/$0.08 per 1M tokens
PLANNING_MODEL=llama-3.1-8b-instant
PLANNING_BASE_URL=https://api.groq.com/openai/v1

# ── LLM Tier 2: Disambiguation & Reasoning ────────────────────────────────────
# Model: meta-llama/llama-4-scout-17b-16e-instruct  |  100% namesake P/R
REASONING_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
REASONING_BASE_URL=https://api.groq.com/openai/v1

# ── LLM Tier 3: Synthesis (richest final profile) ─────────────────────────────
# Model: gpt-4.1-mini (OpenAI)  |  best narrative quality
# Fallback chain: gpt-4.1-mini → llama-4-scout (131k ctx) → llama-3.1-8b
SYNTHESIS_MODEL=gpt-4.1-mini
OPENAI_API_KEY=sk-...         # Required for synthesis (Tier 3) + /sentiment + /influence

# ── Search sources ────────────────────────────────────────────────────────────
TAVILY_API_KEY=tvly-...       # Required for web/news search
APIFY_API_KEY=apify_api_...   # LinkedIn, Twitter, Reddit, Medium, profile images
FIRECRAWL_API_KEY=fc-...      # Deep page extraction
SERPAPI_API_KEY=...            # Google Scholar, Google News, Crunchbase, Patents
SOCIAVAULT_API_KEY=...         # Instagram profiles
GITHUB_TOKEN=ghp_...           # GitHub API (avoids rate limits)
YOUTUBE_API_KEY=...            # YouTube video transcripts

# ── Database (Supabase PostgreSQL) ────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=eyJ...            # Service role key (for Storage writes)

# ── Admin credentials ─────────────────────────────────────────────────────────
ADMIN_EMAIL=admin@discovery.local
ADMIN_PASSWORD=changeme123
JWT_SECRET_KEY=your-secure-random-secret-here

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:3000,https://your-app.vercel.app
CORS_ALLOW_REGEX=https://your-app.*\.vercel\.app

# ── CRM + Slack (optional) ────────────────────────────────────────────────────
HUBSPOT_API_KEY=pat-na1-...
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=xoxb-...

# ── Guardrails ────────────────────────────────────────────────────────────────
MAX_CONCURRENT_JOBS=5
MAX_DAILY_DISCOVERIES=100

# ── Observability ─────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
SENTRY_DSN=
ENVIRONMENT=development
```

### Frontend (`frontend/.env.local`)

```env
# Server-side proxy target. Never exposed to the browser.
BACKEND_URL=http://localhost:8000
# Production (set in Vercel dashboard):
# BACKEND_URL=https://people-discovery-agent-production.up.railway.app
```

---

## API Reference

Base URL: `https://people-discovery-agent-production.up.railway.app`

**Authentication** — JWT Bearer token required for most endpoints:
```
Authorization: Bearer <access_token>
```
API keys (created via `/api/api-keys`) can be used instead for programmatic access:
```
X-API-Key: dk_...
```

---

### Health

#### `GET /api/health`
No auth required.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/health
```
```json
{"status": "healthy", "version": "2.0.0", "timestamp": 1741612345.6, "database": "ok"}
```

---

### Authentication

#### `POST /api/auth/login`
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
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```
Returns new `access_token` and `refresh_token`.

---

### Discovery

#### `POST /api/discover`
Start a single person discovery job. Returns immediately with a `job_id` to poll.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/discover \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "name": "Prashant Parashar",
    "company": "Delhivery",
    "role": "CTO",
    "location": "India",
    "linkedin_url": "",
    "twitter_handle": "",
    "github_username": "",
    "instagram_handle": "",
    "context": "Previously worked at Ola and Zomato as engineering leader"
  }'
```
All fields except `name` are optional. Returns `429` when concurrent or daily limits are exceeded.

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "running",
  "message": "Discovery started. Poll GET /api/jobs/{job_id} for status."
}
```

#### `POST /api/discover/batch`
Enqueue up to 20 discovery jobs at once.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/discover/batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "persons": [
      {"name": "Sam Altman", "company": "OpenAI"},
      {"name": "Jensen Huang", "company": "NVIDIA"}
    ]
  }'
```
```json
{
  "jobs": [
    {"job_id": "uuid-1", "name": "Sam Altman", "status": "running"},
    {"job_id": "uuid-2", "name": "Jensen Huang", "status": "running"}
  ],
  "total": 2
}
```

---

### Jobs

#### `GET /api/jobs/{job_id}`
Poll job status. Completed jobs include full profile in `profile` field.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/jobs/<job_id> \
  -H "Authorization: Bearer <token>"
```
```json
{
  "id": "3fa85f64-...",
  "status": "completed",
  "person_id": "a1b2c3d4-...",
  "total_cost": 0.0028,
  "latency_ms": 89012,
  "sources_hit": 34,
  "cache_hits": 0,
  "cost_breakdown": {
    "planner":     {"cost": 0.000021, "model": "llama-3.1-8b-instant"},
    "source_scorer": {"cost": 0.000015, "model": "llama-3.1-8b-instant"},
    "analyzer":    {"cost": 0.000062, "model": "meta-llama/llama-4-scout-17b-16e-instruct"},
    "synthesizer": {"cost": 0.000137, "model": "openai/gpt-oss-20b"},
    "total": 0.000235
  },
  "created_at": "2026-03-12T10:00:00Z",
  "completed_at": "2026-03-12T10:01:29Z"
}
```

---

### Persons CRUD

#### `GET /api/persons`
List all persons. Query params: `skip`, `limit` (max 100), `search`.

```bash
curl "https://people-discovery-agent-production.up.railway.app/api/persons?search=Prashant&limit=10" \
  -H "Authorization: Bearer <token>"
```
```json
{
  "items": [{
    "id": "a1b2c3d4-...",
    "name": "Prashant Parashar",
    "company": "Delhivery",
    "current_role": "Senior Vice President & Head of Technology",
    "confidence_score": 1.0,
    "status": "discovered",
    "sources_count": 48
  }],
  "total": 1,
  "page": 1,
  "per_page": 20
}
```

#### `GET /api/persons/{id}`
Full profile with all sources.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id> \
  -H "Authorization: Bearer <token>"
```
Returns complete profile: bio, career_timeline, education, expertise, key_facts, notable_work, social_links, sources (array), jobs history.

#### `PUT /api/persons/{id}`
Update editable fields. Updatable: `name`, `current_role`, `company`, `location`, `bio`.

```bash
curl -X PUT https://people-discovery-agent-production.up.railway.app/api/persons/<id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"current_role": "Group CTO", "bio": "Updated bio..."}'
```

#### `DELETE /api/persons/{id}`
Delete person and all associated data.

```bash
curl -X DELETE https://people-discovery-agent-production.up.railway.app/api/persons/<id> \
  -H "Authorization: Bearer <token>"
```
```json
{"deleted": true}
```

#### `POST /api/persons/{id}/re-search`
Re-run discovery using existing profile as context.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/<id>/re-search \
  -H "Authorization: Bearer <token>"
```
```json
{"job_id": "new-uuid", "status": "running", "message": "Re-search started."}
```

#### `POST /api/persons/{id}/refresh-image`
Clear the stored profile image and re-resolve it from scratch (LinkedIn → Wikipedia → Knowledge Graph waterfall). Useful when the current image is wrong (group photo, news photo, etc.).

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/<id>/refresh-image \
  -H "Authorization: Bearer <token>"
```
```json
{
  "person_id": "cb8a7ef8-...",
  "name": "Sam Altman",
  "image_url": "https://fpnlljelpepsjeznobhl.supabase.co/storage/v1/object/public/profile-images/sam-altman-d032b9ad.jpg",
  "message": "Image refreshed successfully."
}
```

---

### Profile Retrieval APIs

Two purpose-built read endpoints for consuming profile data — one for full data, one for selective field access with provenance.

#### `GET /api/persons/{id}/summary`
Returns the **complete profile** of a person — all fields, no source list attached. Ideal for cards, CRM sync, and display pages.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id>/summary \
  -H "Authorization: Bearer <token>"
```
```json
{
  "id": "cb8a7ef8-...",
  "name": "Sam Altman",
  "current_role": "Chief Executive Officer (CEO) and Co-Founder",
  "company": "OpenAI",
  "location": "San Francisco, California, United States",
  "image_url": "https://...supabase.co/.../sam-altman.jpg",
  "bio": "Full biography text...",
  "expertise": ["Artificial Intelligence", "Machine Learning", "Startup Acceleration"],
  "key_facts": ["Co-founded OpenAI in 2015", "Previously president of Y Combinator"],
  "notable_work": ["Leading development of ChatGPT", "Driving GPT-4 advancements"],
  "education": ["Computer Science (incomplete), Stanford University"],
  "career_timeline": [
    {"type": "role", "title": "Co-Founder and CEO", "company": "OpenAI", "start_date": "2015", "end_date": "Present"}
  ],
  "social_links": {"linkedin": "https://www.linkedin.com/in/sam-altman", "twitter": "https://x.com/sama"},
  "confidence_score": 0.808,
  "reputation_score": null,
  "sources_count": 67,
  "last_updated": "2026-03-14T10:58:34.952435+00:00"
}
```

#### `GET /api/persons/{id}/fields?fields=name,current_role,company,...`
Returns **only the fields you request**, each annotated with its top sources and a per-field confidence score. Source ranking is field-aware: `current_role` surfaces LinkedIn first, `bio` surfaces Wikipedia, `notable_work` surfaces news.

**Available fields:** `name`, `current_role`, `company`, `location`, `bio`, `image_url`, `education`, `key_facts`, `social_links`, `expertise`, `notable_work`, `career_timeline`, `confidence_score`, `reputation_score`, `status`, `version`, `created_at`, `updated_at`

```bash
curl "https://people-discovery-agent-production.up.railway.app/api/persons/<id>/fields?fields=name,current_role,company,location" \
  -H "Authorization: Bearer <token>"
```
```json
{
  "id": "cb8a7ef8-...",
  "person": {
    "name": "Sam Altman",
    "company": "OpenAI",
    "current_role": "Chief Executive Officer (CEO) and Co-Founder"
  },
  "overall_confidence": 0.808,
  "total_sources": 67,
  "fields": {
    "name": {
      "value": "Sam Altman",
      "confidence_score": 0.964,
      "sources": [
        {
          "platform": "crunchbase",
          "source_type": "crunchbase",
          "url": "https://www.crunchbase.com/person/sam-altman",
          "title": "Sam Altman - CEO & Co-Founder @ OpenAI",
          "confidence_score": 0.98,
          "relevance_score": 1.0,
          "source_reliability": 0.95,
          "scorer_reason": "Direct LinkedIn profile for the exact target person",
          "fetched_at": "2026-03-13T13:15:25Z"
        }
      ]
    },
    "current_role": {
      "value": "Chief Executive Officer (CEO) and Co-Founder",
      "confidence_score": 0.964,
      "sources": [ "..." ]
    }
  }
}
```

---

### Export

#### `GET /api/persons/{id}/export`
Export profile in one of four formats.

| `format` | MIME type | Description |
|----------|-----------|-------------|
| `json` (default) | application/json | Full profile as JSON file |
| `csv` | text/csv | Fields + sources table |
| `pdf` | application/pdf | Styled A4 report |
| `pptx` | application/vnd.openxmlformats-... | 3-slide deck (title, bio/facts, career) |

```bash
# PDF
curl "https://people-discovery-agent-production.up.railway.app/api/persons/<id>/export?format=pdf" \
  -H "Authorization: Bearer <token>" -o profile.pdf

# PPTX
curl "https://people-discovery-agent-production.up.railway.app/api/persons/<id>/export?format=pptx" \
  -H "Authorization: Bearer <token>" -o profile.pptx

# CSV
curl "https://people-discovery-agent-production.up.railway.app/api/persons/<id>/export?format=csv" \
  -H "Authorization: Bearer <token>" -o profile.csv
```

---

### Intelligence Endpoints

On-demand AI analysis of a discovered person's stored sources. Sentiment and influence endpoints use OpenAI `gpt-4.1-mini`; all pipeline-stage analysis uses Groq. All require auth.

#### `GET /api/persons/{id}/sentiment`
```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id>/sentiment \
  -H "Authorization: Bearer <token>"
```
```json
{
  "overall_sentiment": "positive",
  "sentiment_score": 0.85,
  "public_perception": "Widely regarded as a strong technical leader...",
  "source_sentiments": [{"source": "LinkedIn", "sentiment": "positive", "key_phrases": ["visionary"]}],
  "controversy_flags": [],
  "strengths_in_perception": ["Technical depth"],
  "risks": []
}
```

#### `GET /api/persons/{id}/influence`
```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id>/influence \
  -H "Authorization: Bearer <token>"
```
```json
{
  "overall_influence_score": 78,
  "dimensions": {
    "industry_impact": {"score": 80, "reasoning": "..."},
    "thought_leadership": {"score": 75, "reasoning": "..."},
    "network_reach": {"score": 65, "reasoning": "..."},
    "innovation": {"score": 80, "reasoning": "..."},
    "media_presence": {"score": 60, "reasoning": "..."},
    "community_contribution": {"score": 70, "reasoning": "..."}
  },
  "key_influence_areas": ["Logistics tech", "Engineering leadership"]
}
```

#### `POST /api/persons/relationships`
Map relationship between two persons.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/relationships \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"person_a_id": "<uuid-A>", "person_b_id": "<uuid-B>"}'
```
```json
{
  "relationship_type": "professional",
  "connection_strength": "moderate",
  "shared_contexts": ["Indian startup ecosystem"],
  "potential_connection_points": ["Both led engineering at scale"],
  "relationship_summary": "Both are senior technology leaders in Indian tech..."
}
```

#### `POST /api/persons/{id}/meeting-prep`
Generate meeting preparation notes.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/<id>/meeting-prep \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"context": "Partnership discussion for AI-powered logistics software"}'
```
```json
{
  "executive_summary": "Senior tech executive with deep logistics background...",
  "key_talking_points": ["Their AI automation work at Delhivery"],
  "potential_interests": ["Scaling logistics platforms"],
  "conversation_starters": ["What was the hardest scaling challenge at Delhivery?"],
  "areas_to_avoid": [],
  "recommended_approach": "Lead with technical depth."
}
```

#### `GET /api/persons/{id}/verify`
Cross-reference facts and flag inconsistencies.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id>/verify \
  -H "Authorization: Bearer <token>"
```
```json
{
  "verified_facts": ["CTO at Delhivery confirmed across 4 sources"],
  "inconsistencies": [],
  "data_gaps": ["Education details sparse"],
  "verification_summary": "High confidence profile — 19 facts verified across multiple independent sources."
}
```

---

### Lists

Group persons into named, color-coded collections. All require auth.

#### `GET /api/lists`
```bash
curl https://people-discovery-agent-production.up.railway.app/api/lists \
  -H "Authorization: Bearer <token>"
```
```json
{
  "items": [{"id": "list-uuid", "name": "Tech CTOs India", "color": "#3B82F6", "person_count": 1}]
}
```

#### `POST /api/lists`
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/lists \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "Tech CTOs India", "description": "Top tech leaders", "color": "#3B82F6"}'
```

#### `PUT /api/lists/{list_id}` / `DELETE /api/lists/{list_id}`
Update or delete a list.

#### `GET /api/lists/{list_id}/persons`
Persons in a list. Query params: `page`, `per_page`.

#### `POST /api/lists/{list_id}/persons`
Add persons to a list.
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/lists/<list_id>/persons \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"person_ids": ["uuid-1", "uuid-2"]}'
```
```json
{"added": 2, "person_ids": ["uuid-1", "uuid-2"]}
```

#### `DELETE /api/lists/{list_id}/persons/{person_id}`
Remove a person from a list.

---

### Notes

Private notes per person. All require auth.

#### `GET /api/persons/{id}/notes`
```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id>/notes \
  -H "Authorization: Bearer <token>"
```
```json
{"items": [{"id": "note-uuid", "content": "Met at TechSparks 2025...", "created_at": "..."}]}
```

#### `POST /api/persons/{id}/notes`
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/<id>/notes \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"content": "Met at TechSparks 2025. Interested in AI tooling."}'
```

#### `PUT /api/notes/{note_id}` / `DELETE /api/notes/{note_id}`
Update or delete a note.

---

### Tags

Freeform tags per person. All require auth.

#### `GET /api/persons/{id}/tags`
```bash
curl https://people-discovery-agent-production.up.railway.app/api/persons/<id>/tags \
  -H "Authorization: Bearer <token>"
```
```json
{"tags": ["logistics-cto", "india-tech-leader", "delhivery"]}
```

#### `POST /api/persons/{id}/tags`
Pass an **array** of tags to add in a single request.
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/<id>/tags \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"tags": ["logistics-cto", "india-tech-leader"]}'
```
```json
{"added": ["logistics-cto", "india-tech-leader"]}
```

#### `DELETE /api/persons/{id}/tags/{tag}`
Remove a single tag.

#### `GET /api/tags`
All distinct tags across all persons (for tag cloud / filter UI).
```bash
curl https://people-discovery-agent-production.up.railway.app/api/tags \
  -H "Authorization: Bearer <token>"
```
```json
{"items": [{"tag": "logistics-cto", "person_count": 1}, {"tag": "india-tech-leader", "person_count": 1}]}
```

---

### Public Sharing

Generate a token-based, auth-free shareable link for any profile.
The frontend renders it at `/profile/[token]`.

#### `POST /api/persons/{id}/share`
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/persons/<id>/share \
  -H "Authorization: Bearer <token>"
```
```json
{
  "share_token": "q2iTET4sEnPOWAJq...",
  "url": "https://people-discovery-agent-production.up.railway.app/api/public/q2iTET4sEnPOWAJq..."
}
```
The public profile page URL: `https://frontend-theta-seven-44.vercel.app/profile/q2iTET4sEnPOWAJq...`

#### `GET /api/public/{share_token}`
Fetch the public profile. **No auth required.**
```bash
curl https://people-discovery-agent-production.up.railway.app/api/public/<share_token>
```
Returns: name, current_role, company, location, bio, expertise, education, career_timeline, social_links, sources (no internal metadata).

#### `DELETE /api/persons/{id}/share`
Revoke the share link.
```bash
curl -X DELETE https://people-discovery-agent-production.up.railway.app/api/persons/<id>/share \
  -H "Authorization: Bearer <token>"
```

---

### CRM Integrations

Push any discovered person directly into your CRM. All require auth.

#### `POST /api/crm/hubspot/push/{person_id}`
Push as a HubSpot contact. Uses `HUBSPOT_API_KEY` env var (or pass in body).

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/crm/hubspot/push/<person_id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{}'
```
```json
{"hubspot_contact_id": "12345678"}
```
Returns `409` if contact already exists in HubSpot.

#### `POST /api/crm/salesforce/push/{person_id}`
Push as a Salesforce lead.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/crm/salesforce/push/<person_id> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"sf_access_token": "00D...", "sf_instance_url": "https://yourorg.my.salesforce.com"}'
```
```json
{"salesforce_lead_id": "00Q..."}
```

#### `GET /api/crm/export-data/{person_id}`
Get person data pre-mapped to both CRM schemas.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/crm/export-data/<person_id> \
  -H "Authorization: Bearer <token>"
```
```json
{
  "person_id": "uuid",
  "hubspot": {
    "firstname": "Prashant", "lastname": "Parashar",
    "company": "Delhivery", "jobtitle": "Senior Vice President & Head of Technology",
    "description": "Prashant Parashar is a seasoned technology executive...",
    "city": "Bengaluru, Karnataka, India"
  },
  "salesforce": {
    "FirstName": "Prashant", "LastName": "Parashar",
    "Company": "Delhivery", "Title": "Senior Vice President & Head of Technology"
  }
}
```

---

### Slack Integration

Trigger discovery from any Slack channel via `/discover <name>`. Results posted as Block Kit cards.

#### `POST /api/slack/command`
Slack slash command receiver verified via HMAC-SHA256 (`X-Slack-Signature`).
This endpoint is called by Slack's infrastructure — configure it in your Slack app.

**Setup:**
1. Create a Slack App at https://api.slack.com/apps
2. Add a `/discover` slash command pointing to `https://your-backend.railway.app/api/slack/command`
3. Copy the Signing Secret → set `SLACK_SIGNING_SECRET` in backend env
4. Set `SLACK_BOT_TOKEN` if needed

**Usage in Slack:**
```
/discover Prashant Parashar
```
The bot immediately acknowledges, runs discovery in the background, then posts the result card.

---

### Admin

#### `GET /api/admin/costs`
Cost dashboard.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/admin/costs \
  -H "Authorization: Bearer <token>"
```
```json
{
  "total_spend": 0.0434,
  "total_jobs": 10,
  "average_cost": 0.0043,
  "recent_jobs": [{"id": "uuid", "total_cost": 0.015, "latency_ms": 89012, "sources_hit": 34, "cache_hits": 0}]
}
```

#### `GET /api/admin/analytics`
Aggregated discovery stats.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/admin/analytics \
  -H "Authorization: Bearer <token>"
```
```json
{
  "total_persons": 5,
  "total_sources": 240,
  "total_discoveries": 10,
  "discoveries_last_7_days": 3,
  "top_searched_companies": [{"company": "Delhivery", "count": 2}],
  "source_distribution": {"web": 120, "linkedin_profile": 40},
  "avg_confidence_score": 0.87
}
```

#### `GET /api/admin/rate-limits`
Per-source rate limit status.

```bash
curl https://people-discovery-agent-production.up.railway.app/api/admin/rate-limits \
  -H "Authorization: Bearer <token>"
```

#### `GET /api/admin/audit`
Full audit log of all admin actions (create, update, delete, share, etc.) with user, IP, timestamp.

```bash
curl "https://people-discovery-agent-production.up.railway.app/api/admin/audit?limit=50" \
  -H "Authorization: Bearer <token>"
```
```json
{
  "items": [
    {"action": "create", "target_type": "saved_list", "user_email": "admin@discovery.local", "created_at": "..."}
  ]
}
```

#### `POST /api/admin/users`
Create a new admin/viewer user. Roles: `admin`, `viewer`, `api_only`.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/admin/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"email": "analyst@company.com", "password": "secure123!", "role": "viewer"}'
```
```json
{"id": "user-uuid", "email": "analyst@company.com", "role": "viewer", "created_at": "..."}
```

#### `GET /api/admin/users`
List all users.

#### `DELETE /api/admin/users/{user_id}`
Delete a user.

#### `POST /api/cache/cleanup`
Purge expired cache entries.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/cache/cleanup \
  -H "Authorization: Bearer <token>"
```
```json
{"cleaned": 47}
```

---

### API Keys

Programmatic keys for integrating without admin credentials. All management requires auth.

#### `GET /api/api-keys`
```bash
curl https://people-discovery-agent-production.up.railway.app/api/api-keys \
  -H "Authorization: Bearer <token>"
```
```json
[{"id": "key-uuid", "name": "Production", "rate_limit_per_day": 1000, "active": true, "usage_count": 127}]
```

#### `POST /api/api-keys`
The raw key is returned **only once** — store it immediately.

```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/api-keys \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "Production", "rate_limit_per_day": 1000}'
```
```json
{"id": "key-uuid", "name": "Production", "key": "dk_abc123...", "rate_limit_per_day": 1000, "active": true}
```

#### `DELETE /api/api-keys/{key_id}`
```bash
curl -X DELETE https://people-discovery-agent-production.up.railway.app/api/api-keys/<key_id> \
  -H "Authorization: Bearer <token>"
```
```json
{"revoked": true}
```

---

### Webhooks

Fired after every completed discovery job. Management requires auth.

#### Webhook Events

| Event | Fired when |
|-------|-----------|
| `job.completed` | New person discovered and profile created |
| `person.updated` | Existing person updated via re-search |

#### Payload
```json
{
  "event": "job.completed",
  "data": {
    "job_id": "uuid", "person_id": "uuid",
    "person_name": "Prashant Parashar",
    "status": "completed", "merged": false,
    "total_cost": 0.015, "latency_ms": 89012,
    "sources_hit": 34, "new_sources_added": 34
  }
}
```

**Signature verification** — every delivery includes `X-Webhook-Signature: t=<timestamp>,v1=<hmac_sha256>`.
Verify with: `HMAC-SHA256(secret, f"{timestamp}.{body}")`

#### `GET /api/webhooks`
#### `POST /api/webhooks`
```bash
curl -X POST https://people-discovery-agent-production.up.railway.app/api/webhooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"url": "https://your-server.com/hooks", "secret": "your-secret", "events": ["job.completed", "person.updated"]}'
```
```json
{"id": "wh-uuid", "url": "https://your-server.com/hooks", "events": ["job.completed", "person.updated"], "active": true}
```

#### `DELETE /api/webhooks/{webhook_id}`
Returns `{"deactivated": true}`.

#### `GET /api/webhooks/{webhook_id}/deliveries`
Last 50 delivery attempts with status code, success flag, retry count.

---

### Suggest / Typeahead

#### `GET /api/suggest`
No auth required.

Query params: `q` (min 1 char), `type` (`person` or `company`, default `person`), `limit` (1-20, default 5).

```bash
curl "https://people-discovery-agent-production.up.railway.app/api/suggest?q=Prash&type=person"
```
```json
[{"id": "a1b2c3d4-...", "name": "Prashant Parashar", "company": "Delhivery"}]
```

---

## LLM Strategy

The pipeline uses a **hybrid Groq + OpenAI** architecture — Groq for ultra-fast planning and reasoning, OpenAI for highest-quality synthesis.

### Three-Tier Architecture

| Tier | Stage | Model | Provider | Speed | Cost (per 1M tokens) |
|------|-------|-------|----------|-------|---------------------|
| **1 — Planning** | `plan_searches` + `source_scorer` | `llama-3.1-8b-instant` | Groq | 560 TPS | $0.05 in / $0.08 out |
| **2 — Reasoning** | `analyze_results` (disambiguation) | `llama-4-scout-17b-16e-instruct` | Groq | 750 TPS | $0.11 in / $0.34 out |
| **3 — Synthesis** | `synthesize_profile` | `gpt-4.1-mini` | OpenAI | — | $0.40 in / $1.60 out |
| _(on-demand only)_ | `/sentiment`, `/influence` | `gpt-4.1-mini` | OpenAI | — | $0.40 in / $1.60 out |

### Why This Setup

**Tier 1 — `llama-3.1-8b-instant` (Planning & Source Scoring)**
- Generates 8–10 diverse search queries with deduplication and mandatory source coverage
- LLM-powered source confidence scoring: rates each result on `relevance`, `reliability`, and `corroboration`
- Benchmarked at **100% accuracy** detecting irrelevant sources (namesakes, wrong people)
- 560 TPS, ~0.35s latency, $0.000021/call — the cheapest stage by far

**Tier 2 — `llama-4-scout-17b-16e-instruct` (Disambiguation)**
- Determines whether each source refers to the target person or a namesake
- **100% precision and recall** on namesake detection in benchmarks
- Extracts structured facts (role, employer, education, skills) from raw search results
- ~0.62s latency for full disambiguation of 15 sources

**Tier 3 — `gpt-4.1-mini` via OpenAI (Synthesis)**
- Generates the final 400–600 word professional bio, career timeline, key facts
- Best narrative quality and instruction-following for structured profile generation
- **Adaptive token budgeting**: dynamically truncates sources to fit the 128k context window
- Fallback chain on overflow/rate-limit: `gpt-4.1-mini` → `llama-4-scout` (131k ctx) → `llama-3.1-8b`

### Fallback Behaviour
If a model hits rate limits or context overflow, the system automatically falls back:
1. Synthesis: `gpt-4.1-mini` → `llama-4-scout-17b` (Groq, 131k context) → `llama-3.1-8b` (Groq, 128k context)
2. Planning/Scoring: `llama-3.1-8b` → `gpt-4.1-mini` (OpenAI)
3. Reasoning: `llama-4-scout` → `llama-3.1-8b` (Groq)

---

## Caching Strategy

All search results are cached using `SHA-256(query + search_type)` as the key.

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

**Database:** [Supabase](https://supabase.com) (managed PostgreSQL) in production; SQLite for local development.  
**Image storage:** Supabase Storage bucket `person-images` — profile photos are downloaded on discovery and stored permanently. The `persons.profile_image_url` field points to the public CDN URL.

| Table | Purpose |
|-------|---------|
| `persons` | Core profiles (bio, career, social links, confidence/reputation scores, version, `profile_image_url`) |
| `person_sources` | Individual source results per person (URL, content, `confidence_score`, `confidence_reason`) |
| `person_versions` | Snapshot history after each discovery/re-search |
| `discovery_jobs` | Job tracking (status, cost, latency, cache hits, error) |
| `api_keys` | Hashed API keys with rate limits and usage |
| `api_usage_logs` | Per-request usage log linked to API key |
| `admin_users` | Admin accounts (hashed passwords, roles) |
| `webhook_endpoints` | Registered webhook URLs with event filter and secret |
| `webhook_deliveries` | Delivery attempt log (status code, retries, success) |
| `search_cache` | Cached results keyed by (query_hash, source_type) |
| `saved_lists` | Named, color-coded person groups |
| `person_list_items` | Many-to-many: persons ↔ lists |
| `person_notes` | Private notes per person |
| `person_tags` | Freeform tags per person |
| `audit_logs` | Admin action history (user, action, target, IP, timestamp) |
| `public_shares` | Share tokens for public profile links |

---

## License

MIT
