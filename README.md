# People Discovery Platform

API-first deep person intelligence engine that searches 16+ sources to build comprehensive profiles.

## Architecture

- **Backend**: FastAPI + LangGraph + SQLAlchemy 2.0
- **Frontend**: Next.js 14 + Tailwind CSS
- **Deployment**: Railway (backend) + Vercel (frontend)

## Features

### Page 1: API Demo
- Structured input form (name, company, role, LinkedIn URL, etc.)
- Live curl command generator
- Real-time job polling with progress indicator
- Person profile display with source tabs

### Page 2: Admin Dashboard (Authenticated)
- Person list with search/filter and pagination
- Person detail with tabbed source viewer and version history
- Edit & re-search with corrections
- Export to JSON, CSV, or PDF
- Cost tracking dashboard
- Batch discovery (multi-person CSV upload)
- Person comparison side-by-side
- API key management
- Webhook endpoint management
- API documentation reference

### 16 Deep Search Sources

| Source | Tool | Cost |
|--------|------|------|
| Web Search | Tavily API | $0.016/query |
| News | Tavily (news mode) | $0.016/query |
| Academic | Tavily + SerpAPI | $0.026/query |
| LinkedIn Profile | Apify DataWeave | $0.002/profile |
| LinkedIn Posts | Apify Posts Scraper | $0.0035/post |
| Twitter/X | Apify Scraper | $0.0004/tweet |
| YouTube | youtube-transcript-api | Free |
| GitHub | GitHub REST API | Free |
| Reddit | Apify Scraper | $0.003/result |
| Medium | Apify Scraper | $0.002/article |
| Google Scholar | SerpAPI | $0.01/lookup |
| Instagram | SociaVault | $0.005/profile |
| Google News | SerpAPI | $0.01/query |
| Crunchbase | SerpAPI | $0.01/query |
| Patents | SerpAPI | $0.01/query |
| StackOverflow | SerpAPI | $0.01/query |

**Plus** deep page extraction via Firecrawl for top web/news URLs.

**Average cost per discovery: ~$0.05–$0.25 (first run), ~$0.01 (cached)**

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- SQLite (default, zero-config) or PostgreSQL for production

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env.local
# Edit BACKEND_URL if not using localhost:8000
npm run dev
```

## API Reference

### POST /api/discover
Start a person discovery job.

```bash
curl -X POST http://localhost:8000/api/discover \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "company": "Acme Corp",
    "role": "CTO",
    "location": "San Francisco",
    "linkedin_url": "",
    "twitter_handle": "",
    "github_username": "",
    "context": ""
  }'
```

Response:
```json
{
  "job_id": "uuid",
  "status": "running",
  "message": "Discovery started. Poll GET /api/jobs/{job_id} for status."
}
```

### POST /api/discover/batch
Enqueue multiple discovery jobs at once.

```bash
curl -X POST http://localhost:8000/api/discover/batch \
  -H "Content-Type: application/json" \
  -d '{"persons": [{"name": "Alice"}, {"name": "Bob"}]}'
```

### GET /api/jobs/{job_id}
Poll discovery job status.

Response when complete:
```json
{
  "id": "uuid",
  "status": "completed",
  "person_id": "uuid",
  "total_cost": 0.12,
  "latency_ms": 45000,
  "sources_hit": 15,
  "profile": { "..." : "..." }
}
```

### GET /api/persons
List discovered persons (paginated). Query params: `skip`, `limit`, `search`.

### GET /api/persons/{id}
Get full person profile with all sources.

### PUT /api/persons/{id}
Update person profile fields.

### DELETE /api/persons/{id}
Delete person and all associated data.

### POST /api/persons/{id}/re-search
Re-run discovery using current person data as context.

### GET /api/persons/{id}/export
Export person profile. Query param: `format=json|csv|pdf`.

### GET /api/suggest
Autocomplete person names. Query param: `q=<prefix>`.

### POST /api/auth/login
Admin login.
```json
{ "email": "admin@discovery.local", "password": "changeme123" }
```

### POST /api/auth/refresh
Refresh JWT access token using refresh token.

### GET /api/admin/costs
Cost dashboard statistics (requires auth).

### GET /api/api-keys
List API keys (requires auth).

### POST /api/api-keys
Create a new API key (requires auth).

### DELETE /api/api-keys/{key_id}
Revoke an API key (requires auth).

### GET /api/webhooks
List webhook endpoints (requires auth).

### POST /api/webhooks
Register a webhook endpoint (requires auth).

### DELETE /api/webhooks/{endpoint_id}
Delete a webhook endpoint (requires auth).

## Tech Stack

| Layer | Technology |
|-------|-------------|
| Frontend | Next.js 14, React 18, Tailwind CSS |
| Backend | FastAPI, LangGraph, SQLAlchemy 2.0 |
| Database | SQLite + aiosqlite (default) / PostgreSQL + asyncpg (production) |
| LLMs | GPT-4.1 Mini (planning/analysis/sentiment), DeepSeek V3 / Claude (synthesis) |
| Search | Tavily, Apify, SerpAPI, Firecrawl, SociaVault, GitHub API |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Deploy | Railway (backend), Vercel (frontend) |

## Environment Variables

See `backend/.env.example` and `frontend/.env.example`.

## LLM Strategy

The agent runs a 6-node pipeline. Each node uses the appropriate model for the task:

| Stage | Model | Cost (per 1M tokens) |
|-------|-------|---------------------|
| Planner | GPT-4.1 Mini | $0.40 in / $1.60 out |
| Analyzer | GPT-4.1 Mini | $0.40 in / $1.60 out |
| Sentiment | GPT-4.1 Mini | $0.40 in / $1.60 out |
| Synthesizer | DeepSeek V3 (`deepseek-chat`) | $0.14 in / $0.28 out |
| Synthesizer (alt) | Anthropic Claude / GPT-4.1 Mini | varies |

The synthesizer falls back gracefully: DeepSeek → Claude → GPT-4.1 Mini.

## Agent Pipeline

```
plan_searches → execute_searches → analyze_results → enrich_data → analyze_sentiment → synthesize_profile
```

1. **plan_searches** — LLM generates 8–10 targeted queries covering all source types.
2. **execute_searches** — Runs all queries in parallel across 16 tools; gap-fill ensures no cheap/free platform is skipped; deduplicates by URL; deep-extracts top web/news URLs via Firecrawl.
3. **analyze_results** — LLM disambiguates identity, extracts key facts, assigns confidence score.
4. **enrich_data** — Pure Python: builds chronological career timeline, deduplicates facts, computes source diversity.
5. **analyze_sentiment** — LLM scores per-source sentiment and produces overall reputation score (0–100).
6. **synthesize_profile** — LLM generates the final 400–600 word bio, key facts, career timeline, education, social links, and source list.

## Caching Strategy

Search results are cached in SQLite using a SHA-256 hash of `(query, search_type)` as the key.

| Source | Cache TTL |
|--------|------------|
| LinkedIn | 7 days |
| Twitter | 1 day |
| Web / News | 24 hours |
| YouTube | 30 days |
| GitHub | 7 days |
| Reddit | 1 day |
| Scholar | 30 days |
| Default (all others) | 24 hours |

## License

MIT
