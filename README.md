# People Discovery Agent

An AI-powered agent that discovers comprehensive information about any person by searching across LinkedIn, YouTube, GitHub, news articles, academic papers, and the open web — then synthesizes everything into a structured profile with confidence scoring.

Built with **LangGraph** (stateful agent orchestration), **FastAPI** (async backend), and **Next.js 14** (real-time frontend).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend                         │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────────────┐ │
│  │ Chat         │  │ Search         │  │ Person Profile      │ │
│  │ Interface    │  │ Progress       │  │ Card + Sources      │ │
│  └──────┬───────┘  └────────────────┘  └─────────────────────┘ │
│         │ WebSocket                                             │
└─────────┼───────────────────────────────────────────────────────┘
          │
┌─────────┼───────────────────────────────────────────────────────┐
│         ▼          FastAPI Backend                               │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              LangGraph Agent                          │       │
│  │                                                       │       │
│  │  START ──► Plan ──► Search ──► Analyze ──► Confidence │       │
│  │             ▲                                 │       │       │
│  │             │        ┌─── < threshold ────────┘       │       │
│  │             │        ▼                                │       │
│  │             └── Clarify (interrupt, wait for user)    │       │
│  │                      │                                │       │
│  │                      └─── >= threshold ──► Synthesize │       │
│  │                                               │       │       │
│  │                                              END      │       │
│  └──────────────────────────────────────────────────────┘       │
│         │                                                        │
│  ┌──────┼──────────────────────────────────────────────────┐    │
│  │      ▼         Search Tools                              │    │
│  │  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌─────────┐ │    │
│  │  │ Tavily  │  │ YouTube   │  │ GitHub   │  │  News   │ │    │
│  │  │ Web     │  │ Data API  │  │ API      │  │ (Tavily)│ │    │
│  │  └─────────┘  └───────────┘  └──────────┘  └─────────┘ │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  SQLite/PostgreSQL: Sessions • Profiles • Search Cache    │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Multi-source search** — Searches LinkedIn, YouTube, GitHub, news, academic, Crunchbase, blogs, and Twitter in parallel via Tavily + dedicated APIs
- **Agentic clarification loop** — Asks targeted follow-up questions when results are ambiguous (e.g., "Which John Smith? The one at Google or Meta?")
- **Confidence scoring** — Multi-factor scoring (identity consistency, source diversity, information richness, cross-referencing) with visual gauge
- **Real-time streaming** — WebSocket-based status updates as the agent works through each step
- **Multi-provider LLM** — GPT-5-mini (default), Llama 3.3 on Groq (free), or DeepSeek on Together AI — all swappable via env vars
- **Human-in-the-loop** — LangGraph `interrupt()` pauses execution to collect user input, then resumes seamlessly
- **Persistent storage** — SQLite (default) / PostgreSQL for sessions, profiles, and search history
- **Search result caching** — DB-backed TTL cache avoids redundant API calls across sessions
- **Session history** — Browse, reload, and delete past discovery sessions from the sidebar

## Confidence Scoring Algorithm

The confidence score (0–100%) is calculated from four weighted factors:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Identity Consistency | 30% | Single clear match vs multiple ambiguous people |
| Source Diversity | 20% | Found on 2+ platforms (LinkedIn + YouTube + news) |
| Information Richness | 20% | How many profile fields are filled (role, company, education, etc.) |
| Cross-Reference Match | 30% | Details corroborate across independent sources |

If confidence < 65%, the agent asks for clarification (up to 3 rounds).

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Agent Framework | LangGraph | State machine with `interrupt()` for human-in-the-loop |
| Backend | FastAPI + Pydantic | Async Python, WebSocket, typed validation |
| Frontend | Next.js 14 + Tailwind + shadcn/ui | Polished dark UI with real-time updates |
| Database | SQLite + SQLAlchemy 2.0 async | Zero-config persistence, upgradeable to PostgreSQL |
| Caching | DB-backed TTL cache | SHA-256 keyed, configurable expiration |
| Web Search | Tavily API | Parsed content (not just URLs), 1000 free searches/month |
| Video Search | YouTube Data API v3 | Optional, falls back to Tavily |
| Code Search | GitHub API | Free, no API key required |
| LLM (planning) | GPT-5-mini | $0.25/$2.00 per 1M tokens, swappable to Groq/Together |
| LLM (synthesis) | Claude Sonnet 4.5 | Best synthesis quality |
| Deployment | Docker + Railway | Containerized, one-click deploy |

### LLM Provider Options

All providers use OpenAI-compatible APIs — switch with a single env var:

| Provider | Model | Input/1M | Output/1M | Best For |
|----------|-------|----------|-----------|----------|
| **OpenAI** (default) | `gpt-5-mini` | $0.25 | $2.00 | Balanced quality + cost |
| **Groq** | `llama-3.3-70b-versatile` | ~$0.06 | ~$0.06 | Ultra-fast, free tier |
| **Together AI** | `deepseek-ai/DeepSeek-V3` | $0.14 | $0.28 | Cheapest quality option |
| **Together AI** | `Qwen/Qwen2.5-72B-Instruct-Turbo` | ~$0.12 | ~$0.12 | 97% F1 tool accuracy |
| **Anthropic** | `claude-sonnet-4-5-20241022` | $3.00 | $15.00 | Synthesis (default) |

**Estimated cost per query: ~$0.02–0.08** (depending on provider choice)

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- API keys (see below)

### Required API Keys

| Key | Required? | Free Tier | Get it at |
|-----|-----------|-----------|-----------|
| `OPENAI_API_KEY` | Yes (unless using Groq/Together) | Pay-as-you-go | [platform.openai.com](https://platform.openai.com) |
| `TAVILY_API_KEY` | **Yes** | 1000 searches/month | [tavily.com](https://tavily.com) |
| `ANTHROPIC_API_KEY` | Recommended | Pay-as-you-go | [console.anthropic.com](https://console.anthropic.com) |
| `GROQ_API_KEY` | Optional | Free tier available | [console.groq.com](https://console.groq.com) |
| `TOGETHER_API_KEY` | Optional | $5 free credits | [together.ai](https://together.ai) |
| `GITHUB_TOKEN` | Optional | 5000 req/hr (vs 60 unauthenticated) | [github.com/settings/tokens](https://github.com/settings/tokens) |
| `YOUTUBE_API_KEY` | Optional | 10,000 units/day | [console.cloud.google.com](https://console.cloud.google.com) |

### Option A: Automated Setup (recommended)

```bash
git clone <repo-url>
cd people_discovery_agent

# Edit backend/.env with your API keys (created from template on first run)
./setup.sh

# Start backend (Terminal 1)
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Start frontend (Terminal 2)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and start searching.

### Option B: Run the test suite

```bash
# Runs the backend, hits every endpoint, and does a full WebSocket discovery
./test.sh
```

### Option C: Manual Setup

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Edit with your API keys
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### Option D: Docker Compose

```bash
cp backend/.env.example backend/.env
# Fill in API keys

docker compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

### Example: Free-tier setup with Groq

```env
# backend/.env
GROQ_API_KEY=gsk_...
PLANNING_MODEL=llama-3.3-70b-versatile
PLANNING_BASE_URL=https://api.groq.com/openai/v1
SYNTHESIS_MODEL=llama-3.3-70b-versatile
TAVILY_API_KEY=tvly-...
```

No OpenAI or Anthropic keys needed — runs entirely on Groq's free tier.

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/discover` | Create a new discovery session |
| `GET` | `/api/sessions` | List sessions (`?limit=20`) |
| `GET` | `/api/sessions/{id}` | Get session with profile data |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `GET` | `/api/profiles/search?name=X` | Search previously discovered profiles |
| `POST` | `/api/cache/cleanup` | Remove expired cache entries |
| `GET` | `/api/health` | Health check |

### WebSocket Protocol

Connect to `ws://host/api/ws/{session_id}`

**Client → Server:**
```json
{"type": "query", "text": "Find Andrej Karpathy"}
{"type": "clarification_response", "text": "He previously worked at Tesla"}
```

**Server → Client:**
```json
{"type": "status", "step": "execute_searches", "message": "Searching LinkedIn..."}
{"type": "clarification", "question": "Which company?", "suggestions": ["Google", "Meta"]}
{"type": "result", "profile": {...}, "confidence": 0.92}
```

## Project Structure

```
people_discovery_agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app with lifespan (DB init/shutdown)
│   │   ├── config.py               # Settings + LLM factory (get_planning_llm, get_synthesis_llm)
│   │   ├── db.py                   # SQLAlchemy async engine & session factory
│   │   ├── cache.py                # DB-backed TTL cache for search results
│   │   ├── agent/
│   │   │   ├── graph.py            # LangGraph state machine with conditional routing
│   │   │   ├── state.py            # TypedDict agent state definition
│   │   │   └── nodes/
│   │   │       ├── planner.py      # LLM-powered search query generation
│   │   │       ├── searcher.py     # Parallel search execution (Tavily + YouTube + GitHub)
│   │   │       ├── analyzer.py     # Cross-reference analysis and person identification
│   │   │       ├── confidence.py   # Multi-factor confidence scoring
│   │   │       ├── clarifier.py    # Clarification via LangGraph interrupt()
│   │   │       └── synthesizer.py  # Final profile synthesis with premium LLM
│   │   ├── tools/
│   │   │   ├── tavily_search.py    # Tavily web/domain search with caching
│   │   │   ├── youtube_search.py   # YouTube Data API v3
│   │   │   └── github_search.py    # GitHub user/profile search (PAT optional)
│   │   ├── models/
│   │   │   ├── person.py           # PersonProfile, PersonSource Pydantic models
│   │   │   ├── search.py           # SearchQuery, SearchResult Pydantic models
│   │   │   └── db_models.py        # SQLAlchemy ORM (DiscoverySession, PersonProfileRecord, SearchCacheEntry)
│   │   └── api/
│   │       ├── routes.py           # REST endpoints (CRUD sessions, profiles, cache)
│   │       └── websocket.py        # WebSocket handler with DB persistence
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Main page with chat, profile panel, history sidebar
│   │   │   └── layout.tsx          # Root layout and metadata
│   │   ├── components/
│   │   │   ├── chat-interface.tsx   # Chat input, messages, example prompts
│   │   │   ├── person-profile.tsx   # Profile card (bio, facts, expertise, sources)
│   │   │   ├── confidence-score.tsx # Animated circular confidence gauge
│   │   │   ├── source-card.tsx      # Source card with platform icon and relevance
│   │   │   ├── search-progress.tsx  # Step-by-step agent progress indicator
│   │   │   └── session-history.tsx  # Session list with load/delete
│   │   ├── hooks/
│   │   │   └── use-agent.ts        # WebSocket hook for agent communication
│   │   └── lib/
│   │       ├── types.ts            # Shared TypeScript types
│   │       └── utils.ts            # Utilities (cn, confidence labels/colors)
│   ├── package.json
│   ├── Dockerfile
│   ├── .env.example
│   ├── tailwind.config.ts
│   └── next.config.js
├── docker-compose.yml
├── railway.toml                    # Railway deployment (backend)
├── setup.sh                        # One-command setup (venv, deps, env check)
├── test.sh                         # End-to-end test suite (starts server, tests all endpoints)
├── .gitignore
└── README.md
```

## Deployment

### Railway (recommended)

1. Push to GitHub
2. Create a new Railway project
3. Add a service from your repo → Railway auto-detects `railway.toml` and deploys the backend
4. Set environment variables in Railway dashboard:
   - `OPENAI_API_KEY`, `TAVILY_API_KEY`, `ANTHROPIC_API_KEY` (or your provider keys)
   - `CORS_ORIGINS` = your frontend URL
   - `DATABASE_URL` = add a Railway PostgreSQL plugin, or use the SQLite default
5. For the frontend: deploy on **Vercel** (free, optimal for Next.js):
   - Import your repo, set root directory to `frontend`
   - Set `NEXT_PUBLIC_WS_URL` and `NEXT_PUBLIC_API_URL` to your Railway backend URL

### Docker Compose (local)

```bash
cp backend/.env.example backend/.env
# Fill in API keys

docker compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

## Data Persistence

### Database Schema

| Table | Purpose |
|-------|---------|
| `discovery_sessions` | Tracks every discovery request (status, query, profile, timestamps) |
| `person_profiles` | Searchable archive of all discovered profiles |
| `search_cache` | TTL-based cache keyed by SHA-256(query + search_type) |

### Caching Strategy

Search results are cached with a configurable TTL (default: 1 hour). Matching queries return cached results instantly, saving API costs and latency. Configure via `CACHE_TTL_SECONDS` in `.env`.

### Upgrading to PostgreSQL

```bash
# Install the driver
pip install asyncpg

# Update .env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/discovery_db
```

## Design Decisions

1. **LangGraph over LangChain agents** — Explicit state machine gives full control over the clarification loop. ReAct-style agents can't reliably pause for human input and resume with preserved state.

2. **Multi-provider LLM strategy** — Planning/tool-calling steps (3-5x per query) use cheap, fast models via OpenAI-compatible APIs. The single synthesis step uses a premium model. Swapping providers requires changing one env var, not code.

3. **Tavily over raw Google Search** — Returns parsed, clean content (not just URLs), eliminating separate scraping. The free tier (1000/month) covers POC usage.

4. **WebSocket over polling** — Real-time streaming gives immediate feedback as the agent progresses through each step (10-30s total).

5. **Multi-factor confidence scoring** — Computed from measurable signals (source count, platform diversity, information completeness, cross-referencing) rather than an unreliable single LLM-generated number.

6. **SQLite + DB cache over Redis** — Zero-config persistence for POC. Both upgradeable to PostgreSQL/Redis with a single env var change.

## License

MIT
