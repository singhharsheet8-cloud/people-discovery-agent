# People Discovery Agent

An AI-powered agent that discovers comprehensive information about any person by searching across LinkedIn, YouTube, GitHub, news articles, academic papers, and the open web — then synthesizes everything into a structured profile with a multi-factor confidence score.

Built with **LangGraph** for stateful agent orchestration (with human-in-the-loop), **FastAPI** for the async backend, and **Next.js 14** for a real-time streaming frontend.

**Live demo:** Frontend on [Vercel](https://frontend-dj01isx7u-harsheets-projects-33a318bf.vercel.app) | Backend on [Railway](https://railway.app)

---

## How It Works

```
User: "Find Satya Nadella"
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                  LangGraph Agent                     │
│                                                      │
│  1. PLAN    → Generate 6 targeted search queries     │
│  2. SEARCH  → Execute in parallel across 7+ sources  │
│  3. ANALYZE → Cross-reference and identify matches    │
│  4. SCORE   → Multi-factor confidence calculation     │
│       │                                               │
│       ├── confidence ≥ 65% → SYNTHESIZE → profile    │
│       └── confidence < 65% → CLARIFY → ask user      │
│                                  │                    │
│                                  └── loop back to 1   │
└─────────────────────────────────────────────────────┘
         │
         ▼
Result: Structured profile with 95% confidence, 7 sources
```

The agent searches **LinkedIn** (via Tavily domain filter), **YouTube**, **GitHub**, **news**, **academic papers**, **Crunchbase**, **blogs**, and **Twitter/X** — all in parallel. When results are ambiguous (e.g., common names), it asks targeted follow-up questions using LangGraph's `interrupt()` mechanism, then resumes with preserved state.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Multi-source search** | 7+ source types searched in parallel via Tavily + YouTube Data API + GitHub API |
| **Agentic clarification loop** | Asks targeted follow-ups when ambiguous ("Which John Smith — Google or Meta?") |
| **Confidence scoring** | Multi-factor algorithm: identity consistency (30%), source diversity (20%), information richness (20%), cross-referencing (30%) |
| **Real-time streaming** | WebSocket pushes status updates as the agent progresses through each step |
| **Multi-provider LLM** | GPT-5-mini, Llama 3.3 (Groq free tier), DeepSeek V3, Qwen 2.5 — all swappable via env var |
| **Human-in-the-loop** | LangGraph `interrupt()` pauses execution, collects user input, resumes seamlessly |
| **Persistent storage** | SQLite (default) / PostgreSQL for sessions, profiles, and search cache |
| **Session history** | Browse, reload, and delete past discovery sessions from the sidebar |
| **Cross-platform SSL** | `truststore` + `certifi` fallback ensures HTTPS works on macOS, Linux, and Windows |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Agent Framework | **LangGraph** | State machine with `interrupt()` for human-in-the-loop, checkpointing |
| Backend | **FastAPI** + Pydantic v2 | Async Python, native WebSocket, typed request/response validation |
| Frontend | **Next.js 14** + Tailwind CSS | Server components, real-time dark UI, responsive design |
| Database | **SQLite** + SQLAlchemy 2.0 async | Zero-config, upgradeable to PostgreSQL with one env var |
| Caching | DB-backed TTL cache | SHA-256 keyed, configurable expiration, avoids redundant API calls |
| Web Search | **Tavily API** | Returns parsed content (not raw URLs), domain-specific filtering |
| Video Search | **YouTube Data API v3** | Optional, falls back to Tavily YouTube domain filter |
| Code Search | **GitHub API** | PAT optional (60 req/hr free, 5000 with token) |
| LLM (planning) | **GPT-5-mini** | $0.25/$2.00 per 1M tokens — runs 3-5x per query |
| LLM (synthesis) | **GPT-5-mini** / Claude Sonnet 4.5 | Configurable — use best available for final profile |
| Deployment | **Railway** (backend) + **Vercel** (frontend) | Auto-deploy from GitHub on push |

### LLM Provider Options

All providers use OpenAI-compatible APIs — switch with a single env var:

| Provider | Model | Input/1M | Output/1M | Best For |
|----------|-------|----------|-----------|----------|
| **OpenAI** (default) | `gpt-5-mini` | $0.25 | $2.00 | Balanced quality + cost |
| **Groq** | `llama-3.3-70b-versatile` | ~$0.06 | ~$0.06 | Ultra-fast, free tier |
| **Together AI** | `deepseek-ai/DeepSeek-V3` | $0.14 | $0.28 | Cheapest quality option |
| **Together AI** | `Qwen/Qwen2.5-72B-Instruct-Turbo` | ~$0.12 | ~$0.12 | 97% F1 tool accuracy |
| **Anthropic** | `claude-sonnet-4-5-20241022` | $3.00 | $15.00 | Premium synthesis |

**Estimated cost per query: ~$0.02–0.08** depending on provider.

---

## Quick Start

### Prerequisites

- Python 3.10+ (3.11+ recommended)
- Node.js 18+
- API keys (see table below)

### Required API Keys

| Key | Required? | Free Tier | Get it at |
|-----|-----------|-----------|-----------|
| `OPENAI_API_KEY` | Yes (unless using Groq/Together) | Pay-as-you-go | [platform.openai.com](https://platform.openai.com) |
| `TAVILY_API_KEY` | **Yes** | 1000 searches/month | [tavily.com](https://tavily.com) |
| `ANTHROPIC_API_KEY` | Optional | Pay-as-you-go | [console.anthropic.com](https://console.anthropic.com) |
| `GROQ_API_KEY` | Optional | Free tier available | [console.groq.com](https://console.groq.com) |
| `TOGETHER_API_KEY` | Optional | $5 free credits | [together.ai](https://together.ai) |
| `GITHUB_TOKEN` | Optional | 5000 req/hr (vs 60) | [github.com/settings/tokens](https://github.com/settings/tokens) |
| `YOUTUBE_API_KEY` | Optional | 10,000 units/day | [console.cloud.google.com](https://console.cloud.google.com) |

### Option A: One-command setup (recommended)

```bash
git clone https://github.com/singhharsheet8-cloud/people-discovery-agent.git
cd people-discovery-agent

# Creates venv, installs deps, validates API keys
./setup.sh

# Start backend (Terminal 1)
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Start frontend (Terminal 2)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and search for anyone.

### Option B: Run the automated test suite

```bash
# Starts backend, tests all 8 endpoints + full WebSocket discovery
./test.sh
```

Tests include: health check, session CRUD, full WebSocket discovery flow (real LLM + search calls), profile search, and cache cleanup.

### Option C: Manual setup

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Edit with your API keys
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
# Edit backend/.env with your API keys

docker compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

### Free-tier setup (no OpenAI needed)

```env
# backend/.env — runs entirely on Groq's free tier
GROQ_API_KEY=gsk_...
PLANNING_MODEL=llama-3.3-70b-versatile
PLANNING_BASE_URL=https://api.groq.com/openai/v1
SYNTHESIS_MODEL=llama-3.3-70b-versatile
TAVILY_API_KEY=tvly-...
```

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/discover` | Create a new discovery session |
| `GET` | `/api/sessions` | List sessions (`?limit=20`) |
| `GET` | `/api/sessions/{id}` | Get session with full profile data |
| `DELETE` | `/api/sessions/{id}` | Delete a session |
| `GET` | `/api/profiles/search?name=X` | Search previously discovered profiles |
| `POST` | `/api/cache/cleanup` | Remove expired cache entries |
| `GET` | `/api/health` | Health check |

### WebSocket Protocol

Connect to `ws://host/api/ws` or `ws://host/api/ws/{session_id}`

**Client → Server:**

```json
{ "type": "query", "text": "Find Andrej Karpathy" }
{ "type": "clarification_response", "text": "He previously worked at Tesla" }
```

**Server → Client:**

```json
{ "type": "connected", "session_id": "uuid" }
{ "type": "status", "step": "execute_searches", "message": "Searching LinkedIn..." }
{ "type": "clarification", "question": "Which company?", "suggestions": ["Google", "Meta"] }
{ "type": "result", "profile": { "name": "...", "confidence_score": 0.95, ... }, "confidence": 0.95 }
{ "type": "error", "message": "..." }
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Next.js 14 Frontend                         │
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
│  │  START → Plan → Search → Analyze → Confidence Check   │       │
│  │            ▲                            │              │       │
│  │            │     ┌── < threshold ───────┘              │       │
│  │            │     ▼                                     │       │
│  │            └── Clarify (interrupt → wait for user)     │       │
│  │                  │                                     │       │
│  │                  └── ≥ threshold → Synthesize → END    │       │
│  └──────────────────────────────────────────────────────┘       │
│         │                                                        │
│  ┌──────┼──────────────────────────────────────────────────┐    │
│  │      ▼         Search Tools (parallel)                   │    │
│  │  ┌─────────┐ ┌───────────┐ ┌──────────┐ ┌────────────┐ │    │
│  │  │ Tavily  │ │ YouTube   │ │ GitHub   │ │ News/      │ │    │
│  │  │ Web     │ │ Data API  │ │ API      │ │ Academic   │ │    │
│  │  └─────────┘ └───────────┘ └──────────┘ └────────────┘ │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  SQLite / PostgreSQL                                      │    │
│  │  Sessions • Profiles • Search Cache (SHA-256, TTL)        │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
people-discovery-agent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, SSL fix, lifespan (DB init/close)
│   │   ├── config.py               # Settings + LLM factories (get_planning_llm, get_synthesis_llm)
│   │   ├── db.py                   # SQLAlchemy async engine & session factory
│   │   ├── cache.py                # DB-backed TTL cache for search results
│   │   ├── agent/
│   │   │   ├── graph.py            # LangGraph state machine with conditional routing
│   │   │   ├── state.py            # TypedDict agent state definition
│   │   │   └── nodes/
│   │   │       ├── planner.py      # LLM generates targeted search queries
│   │   │       ├── searcher.py     # Parallel execution (Tavily + YouTube + GitHub)
│   │   │       ├── analyzer.py     # Cross-reference analysis, person identification
│   │   │       ├── confidence.py   # Multi-factor confidence scoring algorithm
│   │   │       ├── clarifier.py    # Human-in-the-loop via LangGraph interrupt()
│   │   │       └── synthesizer.py  # Final profile synthesis with LLM
│   │   ├── tools/
│   │   │   ├── tavily_search.py    # Tavily web/domain search with DB caching
│   │   │   ├── youtube_search.py   # YouTube Data API v3 (optional)
│   │   │   └── github_search.py    # GitHub user/profile search (PAT optional)
│   │   ├── models/
│   │   │   ├── person.py           # PersonProfile, PersonSource Pydantic models
│   │   │   ├── search.py           # SearchQuery, SearchResult Pydantic models
│   │   │   └── db_models.py        # SQLAlchemy ORM models
│   │   └── api/
│   │       ├── routes.py           # REST endpoints (CRUD sessions, profiles, cache)
│   │       └── websocket.py        # WebSocket handler with real-time streaming
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # Main page: chat + profile panel + history sidebar
│   │   │   └── layout.tsx          # Root layout with metadata
│   │   ├── components/
│   │   │   ├── chat-interface.tsx   # Chat input with example prompts
│   │   │   ├── person-profile.tsx   # Profile card (bio, facts, expertise, sources)
│   │   │   ├── confidence-score.tsx # Animated circular confidence gauge
│   │   │   ├── source-card.tsx      # Source card with platform icon + relevance
│   │   │   ├── search-progress.tsx  # Step-by-step agent progress indicator
│   │   │   └── session-history.tsx  # Session list with load/delete actions
│   │   ├── hooks/
│   │   │   └── use-agent.ts        # WebSocket hook for agent communication
│   │   └── lib/
│   │       ├── types.ts            # Shared TypeScript types
│   │       └── utils.ts            # Utilities (cn, confidence labels/colors)
│   ├── package.json
│   ├── Dockerfile
│   └── .env.example
├── docker-compose.yml              # Local multi-service orchestration
├── railway.toml                    # Railway deployment config (backend)
├── setup.sh                        # One-command setup (venv, deps, env validation)
├── test.sh                         # Automated test suite (8 tests, full E2E)
├── .gitignore
└── README.md
```

---

## Deployment

### Backend → Railway

1. Go to [railway.app](https://railway.app) and create a new project
2. Click **"Add a Service"** → **"GitHub Repo"**
3. If prompted, install the Railway GitHub App (see below)
4. Select `singhharsheet8-cloud/people-discovery-agent`
5. Railway auto-detects `railway.toml` and builds the backend Dockerfile
6. Go to **Variables** tab and add:
   - `OPENAI_API_KEY`
   - `TAVILY_API_KEY`
   - `PLANNING_MODEL=gpt-5-mini`
   - `SYNTHESIS_MODEL=gpt-5-mini`
   - `CORS_ORIGINS=https://your-frontend.vercel.app`
   - `GITHUB_TOKEN` (optional)
7. Go to **Settings** → **Networking** → **Generate Domain** to get a public URL

### Frontend → Vercel

1. Go to [vercel.com](https://vercel.com) and import the GitHub repo
2. Set **Root Directory** to `frontend`
3. Add environment variables:
   - `NEXT_PUBLIC_WS_URL=wss://your-railway-domain.up.railway.app`
   - `NEXT_PUBLIC_API_URL=https://your-railway-domain.up.railway.app`
4. Deploy — Vercel auto-builds the Next.js app

### Installing the Railway GitHub App

Railway needs the GitHub App to auto-deploy from your repo:

1. Go to [railway.app/new](https://railway.app/new)
2. Click **"Deploy from GitHub Repo"**
3. Click **"Configure GitHub App"** when prompted
4. Select your GitHub account (`singhharsheet8-cloud`)
5. Choose **"Only select repositories"** → pick `people-discovery-agent`
6. Click **Install & Authorize**
7. Return to Railway and select the repo

After installation, Railway auto-deploys on every `git push` to `main`.

### Docker Compose (local alternative)

```bash
cp backend/.env.example backend/.env
# Edit with your API keys

docker compose up --build
# Backend: http://localhost:8000 | Frontend: http://localhost:3000
```

---

## Confidence Scoring Algorithm

The confidence score (0–100%) is computed from four weighted, measurable signals — not an LLM-generated number:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Identity Consistency | 30% | Single clear match vs. multiple ambiguous people |
| Source Diversity | 20% | Found on 2+ platforms (LinkedIn + YouTube + news) |
| Information Richness | 20% | How many profile fields are filled (role, company, education, etc.) |
| Cross-Reference Match | 30% | Details corroborate across independent sources |

If confidence < 65%, the agent asks for clarification (up to 3 rounds before forcing synthesis with available data).

---

## Data Persistence

| Table | Purpose |
|-------|---------|
| `discovery_sessions` | Every discovery request with status, query, profile, timestamps |
| `person_profiles` | Searchable archive of all discovered profiles |
| `search_cache` | TTL-based cache keyed by SHA-256(query + search_type) |

**Upgrading to PostgreSQL:**

```bash
pip install asyncpg
# In .env:
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/discovery_db
```

---

## Design Decisions

1. **LangGraph over LangChain agents** — Explicit state machine gives full control over the clarification loop. ReAct-style agents can't reliably pause for human input and resume with preserved state.

2. **Multi-provider LLM strategy** — Planning/tool-calling steps (3-5x per query) use cheap, fast models. The single synthesis step can use a premium model. Switching providers requires changing one env var, not code.

3. **Tavily over raw Google Search** — Returns parsed, clean content (not just URLs), eliminating the need for separate scraping. The free tier (1000/month) is sufficient for POC usage.

4. **WebSocket over polling** — Real-time streaming provides immediate feedback as the agent progresses through each step (typically 30-90s total).

5. **Multi-factor confidence scoring** — Computed from measurable signals (source count, platform diversity, information completeness, cross-referencing) rather than an unreliable single LLM-generated number.

6. **SQLite + DB cache over Redis** — Zero-config persistence for POC. Upgradeable to PostgreSQL/Redis with a single env var change. No external infrastructure needed to get started.

7. **Cross-platform SSL fix** — `truststore` (OS native cert store) with `certifi` fallback ensures the app works on macOS, Linux, and Windows without manual certificate configuration.

---

## License

MIT
