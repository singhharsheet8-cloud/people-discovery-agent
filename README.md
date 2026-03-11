# People Discovery Platform

API-first deep person intelligence engine that searches 12+ sources to build comprehensive profiles.

## Architecture

- **Backend**: FastAPI + LangGraph + PostgreSQL
- **Frontend**: Next.js 14 + Tailwind CSS
- **Deployment**: Railway (backend) + Vercel (frontend)

## Features

### Page 1: API Demo
- Structured input form (name, company, role, LinkedIn URL, etc.)
- Live curl command generator
- Real-time job polling
- Person profile display with source tabs

### Page 2: Admin Dashboard (Authenticated)
- Person list with search/filter
- Person detail with tabbed source viewer
- Edit & re-search with corrections
- Cost tracking dashboard

### 12 Deep Search Sources

| Source | Tool | Cost |
|--------|------|------|
| Web Search | Tavily API | $0.016/query |
| News | Tavily (news) | $0.016/query |
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

**Average cost per discovery: ~$0.275 (first run), ~$0.01 (cached)**

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL (or use SQLite for development)

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
npm run dev
```

## API Reference

### POST /api/discover
Start person discovery.

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

### GET /api/jobs/{job_id}
Poll discovery job status.

Response when complete:
```json
{
  "id": "uuid",
  "status": "completed",
  "person_id": "uuid",
  "total_cost": 0.275,
  "latency_ms": 45000,
  "sources_hit": 15,
  "profile": { ... }
}
```

### GET /api/persons
List discovered persons (paginated).

### GET /api/persons/{id}
Get full person profile with sources.

### PUT /api/persons/{id}
Update person profile fields.

### DELETE /api/persons/{id}
Delete person and all associated data.

### POST /api/persons/{id}/re-search
Re-run discovery with current person data.

### POST /api/auth/login
Admin login. Body: `{"email": "...", "password": "..."}`.

### GET /api/admin/costs
Cost dashboard statistics.

## Tech Stack

| Layer | Technology |
|-------|-------------|
| Frontend | Next.js 14, React 18, Tailwind CSS |
| Backend | FastAPI, LangGraph, SQLAlchemy 2.0 |
| Database | PostgreSQL (asyncpg) |
| LLMs | GPT-4.1 Mini (planning), DeepSeek V3.2 (synthesis) |
| Search | Tavily, Apify, SerpAPI, Firecrawl, SociaVault |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Deploy | Railway, Vercel |

## Environment Variables

See `backend/.env.example` and `frontend/.env.example`.

## LLM Strategy

| Stage | Model | Cost (per 1M tokens) |
|-------|-------|---------------------|
| Planner | GPT-4.1 Mini | $0.40 in / $1.60 out |
| Analyzer | GPT-4.1 Mini | $0.40 in / $1.60 out |
| Synthesizer | DeepSeek V3.2 | $0.28 in / $0.42 out |

## Caching Strategy

| Source | Cache TTL |
|--------|------------|
| LinkedIn | 7 days |
| Twitter | 1 day |
| Web/News | 24 hours |
| YouTube | 30 days |
| GitHub | 7 days |
| Reddit | 1 day |
| Scholar | 30 days |

## License

MIT
