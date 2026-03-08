# People Discovery Agent

> AI-powered person discovery engine with multi-source search, cross-referencing, and confidence scoring.

Built with **LangGraph** for stateful agentic workflows, **FastAPI** for real-time WebSocket streaming, and **Next.js** for a polished conversational UI.

**Live demo:** [Frontend](https://frontend-chi-gules-87.vercel.app) | [Backend API](https://backend-production-50b0.up.railway.app/api/health)

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
│  │              │ Synthesizer  │←───────│  ≥ threshold?     │  │
│  │              │  (LLM)       │        │  → Clarifier      │  │
│  │              └──────────────┘        │    (interrupt)     │  │
│  │                                      └───────────────────│  │
│  └───────────────────────────────────────────────────────────┘  │
│       │                                                         │
│  ┌────┴──────────────────────────────────────────────────────┐  │
│  │  Search Tools (Parallel)                                   │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────────┐   │  │
│  │  │ Tavily │  │ GitHub │  │YouTube │  │  + 5 more    │   │  │
│  │  │  API   │  │  API   │  │Data API│  │  platforms   │   │  │
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

- **Multi-Source Search** — Parallel searches across LinkedIn, GitHub, YouTube, Twitter, news, academic, and general web via Tavily API
- **Agentic Loop** — LangGraph-powered state machine with human-in-the-loop clarification when results are ambiguous
- **Confidence Scoring** — Multi-factor algorithm (identity consistency, source diversity, information richness, cross-reference match)
- **Real-time Streaming** — WebSocket-based live progress updates as the agent works
- **Caching** — TTL-based search result caching to reduce API costs and improve latency
- **Session Persistence** — Full session history with profile storage and search across past discoveries
- **Retry & Resilience** — Exponential backoff on LLM/API failures, per-search timeouts, graceful degradation
- **Rate Limiting** — Per-IP rate limiting middleware with configurable thresholds
- **Request Tracing** — Unique request IDs for debugging and observability

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Agent Framework | LangGraph | Stateful agent workflow with checkpointing |
| Backend | FastAPI + Uvicorn | Async API server with WebSocket support |
| Frontend | Next.js 14 + Tailwind CSS | Server-rendered React with glassmorphism UI |
| Planning LLM | Llama 3.3 70B (Groq) | Fast, cheap query planning and analysis |
| Synthesis LLM | GPT-4.1 Mini (OpenAI) | High-quality profile synthesis |
| Web Search | Tavily API | Domain-filtered web search with caching |
| Code Search | GitHub API v3 | Developer profile enrichment |
| Database | SQLAlchemy + aiosqlite | Async ORM with SQLite (Postgres-ready) |
| Deployment | Railway + Vercel | Containerized backend + edge frontend |
| CI/CD | GitHub Actions | Lint, type-check, build verification |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- API keys: OpenAI or Groq (LLM) + Tavily (search)

### One-Command Setup

```bash
chmod +x setup.sh && ./setup.sh
```

### Manual Setup

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your API keys
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
echo "NEXT_PUBLIC_WS_URL=ws://localhost:8000/api/ws" > .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api" >> .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Docker Compose

```bash
cp backend/.env.example backend/.env  # Edit with keys
docker compose up --build
```

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

The confidence score (0-100%) is computed from four weighted factors:

| Factor | Weight | Measures |
|--------|--------|----------|
| Identity Consistency | 30% | Single match vs multiple namesakes |
| Source Diversity | 20% | Coverage across distinct platforms |
| Information Richness | 20% | How many profile fields are populated |
| Cross-Reference Match | 30% | Sources confirming the same facts |

## Cost Analysis

| Component | Cost per Query | Monthly (100 queries) |
|-----------|---------------|----------------------|
| Groq (Llama 3.3 70B) | ~$0.002 | $0.20 |
| OpenAI (GPT-4.1 Mini) | ~$0.01 | $1.00 |
| Tavily Search | ~$0.01 | $1.00 |
| **Total** | **~$0.02** | **~$2.20** |

## Project Structure

```
people_discovery_agent/
├── backend/
│   ├── app/
│   │   ├── agent/           # LangGraph agent
│   │   │   ├── graph.py     # State machine definition
│   │   │   ├── state.py     # Agent state schema
│   │   │   └── nodes/       # Agent nodes
│   │   │       ├── planner.py
│   │   │       ├── searcher.py
│   │   │       ├── analyzer.py
│   │   │       ├── confidence.py
│   │   │       ├── clarifier.py
│   │   │       └── synthesizer.py
│   │   ├── api/             # FastAPI routes
│   │   │   ├── routes.py
│   │   │   └── websocket.py
│   │   ├── tools/           # Search integrations
│   │   │   ├── tavily_search.py
│   │   │   ├── github_search.py
│   │   │   └── youtube_search.py
│   │   ├── models/          # Pydantic + SQLAlchemy models
│   │   ├── config.py        # Settings & LLM factories
│   │   ├── db.py            # Database engine
│   │   ├── cache.py         # TTL search cache
│   │   ├── middleware.py    # Rate limit + request ID
│   │   ├── utils.py         # Retry decorator
│   │   └── main.py          # FastAPI app entry
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router
│   │   ├── components/      # React components
│   │   ├── hooks/           # Custom hooks
│   │   └── lib/             # Types & utilities
│   ├── package.json
│   └── Dockerfile
├── .github/workflows/ci.yml # CI pipeline
├── docker-compose.yml
├── Dockerfile               # Railway root Dockerfile
├── setup.sh                 # One-command setup
├── test.sh                  # E2E test script
└── README.md
```

## Environment Variables

See [`backend/.env.example`](backend/.env.example) for all configuration options.

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key |
| `GROQ_API_KEY` | Yes* | Groq API key (fast planning) |
| `TAVILY_API_KEY` | Yes | Web search API |
| `GITHUB_TOKEN` | No | GitHub API (5000 req/hr vs 60) |
| `PLANNING_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `SYNTHESIS_MODEL` | No | Default: `gpt-4.1-mini` |

*At least one LLM provider key required.

## License

MIT
