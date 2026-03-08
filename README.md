# People Discovery Agent

> AI-powered person discovery engine with multi-source search, cross-referencing, and confidence scoring.

Built with **LangGraph** for stateful agentic workflows, **FastAPI** for real-time WebSocket streaming, and **Next.js** for a polished conversational UI.

**Live demo:** [Frontend](https://frontend-chi-gules-87.vercel.app) | [Backend API](https://backend-production-50b0.up.railway.app/api/health) | [API Docs](https://backend-production-50b0.up.railway.app/docs)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                         │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │   Chat   │  │   Profile    │  │  Progress   │  │ Session │ │
│  │Interface │  │   Display    │  │  Tracker    │  │ History │ │
│  └────┬─────┘  └──────────────┘  └─────────────┘  └─────────┘ │
│       │ WebSocket                                               │
└───────┼─────────────────────────────────────────────────────────┘
        │
┌───────┴─────────────────────────────────────────────────────────┐
│                     FastAPI Backend                              │
│  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────┐ │
│  │WebSocket │  │  REST API    │  │Rate Limit│  │  Request   │ │
│  │ Handler  │  │  /sessions   │  │Middleware│  │  ID Track  │ │
│  └────┬─────┘  └──────────────┘  └──────────┘  └────────────┘ │
│       │                                                         │
│  ┌────┴──────────────────────────────────────────────────────┐  │
│  │              LangGraph Agent (Stateful)                    │  │
│  │                                                            │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌─────────┐ │  │
│  │  │ Planner │→│ Searcher  │→│  Analyzer   │→│Confidence│ │  │
│  │  │  (LLM)  │ │(Parallel) │ │   (LLM)    │ │ Scorer   │ │  │
│  │  └─────────┘  └──────────┘  └────────────┘  └────┬────┘ │  │
│  │                                                    │      │  │
│  │              ┌──────────────┐        ┌────────────┘      │  │
│  │              │ Synthesizer  │←───yes──│ ≥ 75% conf?      │  │
│  │              │  (LLM)       │        │  no → Clarifier   │  │
│  │              └──────────────┘        │   (interrupt/HITL) │  │
│  │                                      └───────────────────│  │
│  └───────────────────────────────────────────────────────────┘  │
│       │                                                         │
│  ┌────┴──────────────────────────────────────────────────────┐  │
│  │  Search Tools (Parallel, async)                            │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────────┐   │  │
│  │  │ Tavily │  │ GitHub │  │YouTube │  │  LinkedIn,   │   │  │
│  │  │  API   │  │  API   │  │Data API│  │  News, etc.  │   │  │
│  │  └────────┘  └────────┘  └────────┘  └──────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│       │                                                         │
│  ┌────┴───────────┐  ┌──────────────┐                          │
│  │  SQLite/Postgres│  │  TTL Cache   │                          │
│  │  (Sessions +   │  │  (Search     │                          │
│  │   Profiles)    │  │   Results)   │                          │
│  └────────────────┘  └──────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Multi-Source Search** — Parallel searches across LinkedIn, GitHub, YouTube, news, academic, blogs, and general web via Tavily + dedicated APIs
- **Agentic Clarification Loop** — When confidence is below 75%, the agent asks the user a clarifying question, re-searches with the new context, and re-evaluates (up to 2 rounds)
- **Confidence Scoring** — Multi-factor algorithm: identity consistency (30%), source diversity (20%), information richness (20%), cross-reference match (30%)
- **Real-time Streaming** — WebSocket-based live progress updates as each agent step executes
- **Caching** — DB-backed TTL cache for all search results (Tavily, YouTube, GitHub) with periodic cleanup
- **Session Persistence** — Full session history with profile storage and search across past discoveries
- **LLM Fallback** — Automatic fallback from primary to secondary LLM on rate-limit errors
- **Retry & Resilience** — Exponential backoff on API failures, per-search timeouts, graceful degradation
- **Rate Limiting** — Per-IP rate limiting middleware (60 req/min HTTP, 20/min WebSocket)
- **Request Tracing** — Unique `x-request-id` headers for debugging and observability

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Agent Framework | LangGraph | Stateful agent graph with checkpointing and interrupt |
| Backend | FastAPI + Uvicorn | Async API server with WebSocket support |
| Frontend | Next.js 14 + Tailwind CSS | Server-rendered React with glassmorphism UI |
| Planning LLM | GPT-4.1 Mini (OpenAI) | Fast, cheap query planning and analysis (~$0.40/1M tokens) |
| Synthesis LLM | GPT-5 Mini (OpenAI) | Reasoning model for rich profile synthesis |
| Web Search | Tavily API | Domain-filtered web search (LinkedIn, news, academic, etc.) |
| Video Search | YouTube Data API v3 | Dedicated video/talk discovery |
| Code Search | GitHub API v3 | Developer profile enrichment |
| Database | SQLAlchemy 2.0 + aiosqlite | Async ORM with SQLite (swap to Postgres for production) |
| Deployment | Railway + Vercel | Containerized backend + edge frontend |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- API keys: **OpenAI** (required) + **Tavily** (required)

### One-Command Setup

```bash
git clone https://github.com/singhharsheet8-cloud/people-discovery-agent.git
cd people-discovery-agent
chmod +x setup.sh && ./setup.sh
```

The script will:
1. Check that Python 3.10+ and Node.js 18+ are installed
2. Create a Python virtual environment and install backend dependencies
3. Copy `.env.example` → `.env` (you fill in your API keys)
4. Install frontend dependencies and configure local URLs

After setup, start the app in two terminals:

```bash
# Terminal 1 — Backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and start searching for people.

### Docker Compose

```bash
cp backend/.env.example backend/.env   # Add your API keys
docker compose up --build
```

### Run Tests

```bash
chmod +x test.sh && ./test.sh
```

Runs 8 automated tests: health check, session CRUD, WebSocket discovery flow, profile search, and cache cleanup.

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check with dependency status |
| `POST` | `/api/discover` | Create a new discovery session |
| `GET` | `/api/sessions` | List recent sessions |
| `GET` | `/api/sessions/:id` | Get session details + profile |
| `DELETE` | `/api/sessions/:id` | Delete a session |
| `GET` | `/api/profiles/search?name=` | Search past profiles by name |
| `POST` | `/api/cache/cleanup` | Clean expired cache entries |

### WebSocket Protocol

Connect to `ws://host/api/ws/{session_id}`

**Client → Server:**
```json
{"type": "query", "text": "Satya Nadella CEO Microsoft"}
{"type": "clarification_response", "text": "The one at Microsoft"}
```

**Server → Client:**
```json
{"type": "connected", "session_id": "uuid"}
{"type": "status", "step": "plan_searches", "message": "Planning..."}
{"type": "clarification", "question": "...", "suggestions": [...]}
{"type": "result", "profile": {...}, "confidence": 0.93}
{"type": "error", "message": "..."}
```

## Confidence Scoring

The confidence score (0–100%) is computed from four weighted factors:

| Factor | Weight | Measures |
|--------|--------|----------|
| Identity Consistency | 30% | Single match vs. multiple namesakes |
| Source Diversity | 20% | Coverage across distinct platforms |
| Information Richness | 20% | How many profile fields are populated |
| Cross-Reference Match | 30% | Multiple sources confirming the same facts |

If confidence is **below 75%**, the agent enters a clarification loop — it asks the user a targeted question, re-searches with the new context, and re-evaluates. This repeats up to 2 times before synthesizing the best available profile.

## Cost Analysis

| Component | Cost per Query | Monthly (100 queries) |
|-----------|---------------|----------------------|
| GPT-4.1 Mini (planning + analysis) | ~$0.005 | $0.50 |
| GPT-5 Mini (synthesis) | ~$0.01 | $1.00 |
| Tavily Search (5 queries × $0.002) | ~$0.01 | $1.00 |
| YouTube + GitHub APIs | Free | Free |
| **Total** | **~$0.025** | **~$2.50** |

Costs are per single-turn discovery. Multi-turn (with clarification) costs ~2–3× per additional round.

## Project Structure

```
people_discovery_agent/
├── backend/
│   ├── app/
│   │   ├── agent/              # LangGraph agent
│   │   │   ├── graph.py        # State machine + routing logic
│   │   │   ├── state.py        # Agent state schema (TypedDict)
│   │   │   └── nodes/          # Agent nodes
│   │   │       ├── planner.py      # Generates search queries
│   │   │       ├── searcher.py     # Parallel search execution
│   │   │       ├── analyzer.py     # Cross-references results
│   │   │       ├── confidence.py   # Multi-factor scoring
│   │   │       ├── clarifier.py    # Human-in-the-loop questions
│   │   │       └── synthesizer.py  # Profile generation
│   │   ├── api/                # FastAPI routes
│   │   │   ├── routes.py           # REST endpoints
│   │   │   └── websocket.py       # WebSocket handler
│   │   ├── tools/              # Search integrations
│   │   │   ├── tavily_search.py    # Web/LinkedIn/news/academic
│   │   │   ├── github_search.py    # GitHub user search
│   │   │   └── youtube_search.py   # YouTube Data API v3
│   │   ├── models/             # Pydantic + SQLAlchemy models
│   │   ├── config.py           # Settings & LLM factory functions
│   │   ├── db.py               # Async database engine
│   │   ├── cache.py            # TTL search result cache
│   │   ├── middleware.py       # Rate limit + request ID
│   │   ├── utils.py            # Retry decorator + LLM fallback
│   │   └── main.py             # FastAPI app entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/                # Next.js App Router pages
│   │   ├── components/         # React components (chat, profile, etc.)
│   │   ├── hooks/              # Custom hooks (useDiscovery, etc.)
│   │   └── lib/                # Types & utility functions
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml          # Local multi-service orchestration
├── Dockerfile                  # Root Dockerfile (Railway deployment)
├── setup.sh                    # One-command local setup
├── test.sh                     # Automated E2E test suite (8 tests)
├── railway.toml                # Railway deployment config
└── README.md
```

## Environment Variables

All configuration lives in `backend/.env`. See [`backend/.env.example`](backend/.env.example) for the full template with comments.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | **Yes** | — | OpenAI API key (used for both planning and synthesis) |
| `TAVILY_API_KEY` | **Yes** | — | Tavily web search API key ([get free key](https://tavily.com)) |
| `PLANNING_MODEL` | No | `gpt-4.1-mini` | Model for query planning and analysis |
| `SYNTHESIS_MODEL` | No | `gpt-5-mini` | Model for profile synthesis |
| `PLANNING_BASE_URL` | No | *(OpenAI)* | Override for Groq/Together AI endpoints |
| `GROQ_API_KEY` | No | — | Groq API key (if using Groq for planning) |
| `TOGETHER_API_KEY` | No | — | Together AI key (if using open-source models) |
| `GITHUB_TOKEN` | No | — | GitHub PAT (raises rate limit from 60 → 5000 req/hr) |
| `YOUTUBE_API_KEY` | No | — | YouTube Data API key (falls back to Tavily if unset) |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./discovery.db` | Database connection string |
| `CACHE_TTL_SECONDS` | No | `3600` | Search cache expiration (seconds) |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Allowed CORS origins |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## License

MIT
