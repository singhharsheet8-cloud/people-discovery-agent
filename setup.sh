#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "======================================"
echo "  People Discovery Agent — Setup"
echo "======================================"
echo ""

# ---- Check prerequisites ----
info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install Python 3.10+ from https://python.org"
command -v node    >/dev/null 2>&1 || fail "node not found. Install Node.js 18+ from https://nodejs.org"
command -v npm     >/dev/null 2>&1 || fail "npm not found. Install Node.js 18+ from https://nodejs.org"

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)

ok "Python ${PY_VERSION}"
ok "Node.js $(node -v)"

# ---- Backend setup ----
info "Setting up backend..."

cd "$ROOT/backend"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    ok "Created Python virtual environment"
else
    ok "Virtual environment already exists"
fi

source venv/bin/activate

pip install --quiet --upgrade pip 2>/dev/null || true
pip install --quiet -r requirements.txt
pip install --quiet websockets 2>/dev/null || true
ok "Backend dependencies installed"

# ---- .env file ----
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "Created backend/.env from template"
    echo ""
    echo -e "  ${YELLOW}ACTION REQUIRED: Add your API keys to backend/.env${NC}"
    echo ""
    echo "  Required keys:"
    echo "    OPENAI_API_KEY    — get from https://platform.openai.com/api-keys"
    echo "    TAVILY_API_KEY    — get free key at https://tavily.com"
    echo ""
    echo "  Optional (recommended):"
    echo "    GITHUB_TOKEN      — GitHub PAT for higher rate limits"
    echo "    YOUTUBE_API_KEY   — for dedicated video search"
    echo ""
    echo "  Edit the file, then re-run this script:"
    echo "    nano backend/.env   # or use your editor"
    echo "    ./setup.sh"
    echo ""
    exit 1
else
    ok "backend/.env exists"
fi

# Validate required keys
source .env 2>/dev/null || true

if [ -z "${OPENAI_API_KEY:-}" ] || [ "${OPENAI_API_KEY}" = "sk-..." ]; then
    fail "OPENAI_API_KEY not set. Add it to backend/.env"
fi
ok "OpenAI API key configured"

if [ -z "${TAVILY_API_KEY:-}" ] || [ "${TAVILY_API_KEY}" = "tvly-..." ]; then
    fail "TAVILY_API_KEY not set. Get a free key at https://tavily.com and add to backend/.env"
fi
ok "Tavily API key configured"

# Create data directory for SQLite
mkdir -p "$ROOT/backend/data"

# ---- Frontend setup ----
info "Setting up frontend..."

cd "$ROOT/frontend"

npm install --silent 2>/dev/null
ok "Frontend dependencies installed"

if [ ! -f ".env.local" ]; then
    cp .env.example .env.local
    ok "Created frontend/.env.local (points to localhost:8000)"
else
    ok "frontend/.env.local exists"
fi

# ---- Summary ----
echo ""
echo "======================================"
echo -e "  ${GREEN}Setup complete!${NC}"
echo "======================================"
echo ""
echo "  Start the app in two terminals:"
echo ""
echo "    Terminal 1 (backend):"
echo "      cd backend && source venv/bin/activate"
echo "      uvicorn app.main:app --reload --port 8000"
echo ""
echo "    Terminal 2 (frontend):"
echo "      cd frontend && npm run dev"
echo ""
echo "    Then open http://localhost:3000"
echo ""
echo "  Run the automated test suite:"
echo "      ./test.sh"
echo ""
echo "  Or use Docker Compose:"
echo "      docker compose up --build"
echo ""
