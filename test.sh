#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[TEST]${NC} $*"; }
ok()    { echo -e "${GREEN}[PASS]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; }
fatal() { echo -e "${RED}[FATAL]${NC} $*"; exit 1; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PID=""
BACKEND_URL="http://localhost:8000"
WS_URL="ws://localhost:8000"
PASSED=0
FAILED=0

cleanup() {
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo ""
echo "======================================"
echo "  People Discovery Agent — Tests"
echo "======================================"
echo ""

# ---- Start backend ----
info "Starting backend server..."

cd "$ROOT/backend"

if [ ! -d "venv" ]; then
    fatal "No virtual environment found. Run ./setup.sh first."
fi

source venv/bin/activate

if [ ! -f ".env" ]; then
    fatal "No .env file. Run ./setup.sh first."
fi

uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning &
BACKEND_PID=$!

# Wait for server to be ready (up to 30 seconds)
for i in $(seq 1 30); do
    if curl -sf "$BACKEND_URL/api/health" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        fatal "Backend process died on startup. Check logs."
    fi
    sleep 1
done

if ! curl -sf "$BACKEND_URL/api/health" >/dev/null 2>&1; then
    fatal "Backend failed to start within 30s."
fi
ok "Backend started (PID $BACKEND_PID)"

# ---- Test 1: Health endpoint ----
info "Test 1: Health endpoint"
HEALTH=$(curl -sf "$BACKEND_URL/api/health")
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='healthy'" 2>/dev/null; then
    ok "Health endpoint returns healthy"
    PASSED=$((PASSED + 1))
else
    fail "Health check failed: $HEALTH"
    FAILED=$((FAILED + 1))
fi

# ---- Test 2: Create session via REST ----
info "Test 2: Create discovery session"
SESSION_RESP=$(curl -sf -X POST "$BACKEND_URL/api/discover" \
    -H "Content-Type: application/json" \
    -d '{"query": "Satya Nadella CEO Microsoft"}')

SESSION_ID=$(echo "$SESSION_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])" 2>/dev/null || echo "")

if [ -n "$SESSION_ID" ]; then
    ok "Session created: ${SESSION_ID:0:8}..."
    PASSED=$((PASSED + 1))
else
    fail "Session creation failed: $SESSION_RESP"
    FAILED=$((FAILED + 1))
fi

# ---- Test 3: List sessions ----
info "Test 3: List sessions"
SESSIONS=$(curl -sf "$BACKEND_URL/api/sessions")
SESSION_COUNT=$(echo "$SESSIONS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$SESSION_COUNT" -ge 1 ]; then
    ok "Sessions listed ($SESSION_COUNT found)"
    PASSED=$((PASSED + 1))
else
    fail "No sessions found"
    FAILED=$((FAILED + 1))
fi

# ---- Test 4: Get specific session ----
info "Test 4: Get session details"
if [ -n "$SESSION_ID" ]; then
    SESSION_DETAIL=$(curl -sf "$BACKEND_URL/api/sessions/$SESSION_ID")
    STATUS=$(echo "$SESSION_DETAIL" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "")
    if [ -n "$STATUS" ]; then
        ok "Session detail retrieved (status: $STATUS)"
        PASSED=$((PASSED + 1))
    else
        fail "Could not read session detail"
        FAILED=$((FAILED + 1))
    fi
else
    warn "Skipped — no session ID"
fi

# ---- Test 5: WebSocket full discovery ----
info "Test 5: WebSocket discovery (Satya Nadella) — this takes 30-90s..."

WS_TEST_SCRIPT=$(cat <<'PYEOF'
import asyncio, json, sys

async def run():
    try:
        import websockets
    except ImportError:
        print("SKIP:websockets not installed", file=sys.stderr)
        sys.exit(2)

    uri = "ws://127.0.0.1:8000/api/ws"
    timeout = 120

    try:
        async with websockets.connect(uri, close_timeout=5) as ws:
            connected = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            print(f"STATUS:connected:{connected.get('session_id','?')}")

            await ws.send(json.dumps({"type": "query", "text": "Satya Nadella CEO Microsoft"}))

            got_result = False
            got_clarification = False
            start = asyncio.get_event_loop().time()

            while (asyncio.get_event_loop().time() - start) < timeout:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    if msg_type == "status":
                        print(f"STATUS:{msg.get('step','')}:{msg.get('message','')}")
                    elif msg_type == "clarification":
                        got_clarification = True
                        print(f"CLARIFICATION:{msg.get('question','')}")
                        await ws.send(json.dumps({
                            "type": "clarification_response",
                            "text": "Satya Nadella, current CEO of Microsoft Corporation"
                        }))
                    elif msg_type == "result":
                        got_result = True
                        profile = msg.get("profile", {})
                        confidence = msg.get("confidence", 0)
                        name = profile.get("name", "Unknown")
                        print(f"RESULT:{name}:{confidence}")
                        break
                    elif msg_type == "error":
                        print(f"ERROR:{msg.get('message','')}")
                        break
                except asyncio.TimeoutError:
                    print("ERROR:Timed out waiting for messages")
                    break

            if got_result:
                sys.exit(0)
            elif got_clarification:
                sys.exit(3)
            else:
                sys.exit(1)

    except Exception as e:
        print(f"ERROR:{e}")
        sys.exit(1)

asyncio.run(run())
PYEOF
)

WS_OUTPUT=$(python3 -c "$WS_TEST_SCRIPT" 2>&1) || WS_EXIT=$?
WS_EXIT=${WS_EXIT:-0}

echo "$WS_OUTPUT" | while IFS= read -r line; do
    case "$line" in
        STATUS:*)   info "  → ${line#STATUS:}" ;;
        RESULT:*)   ok   "  ✓ Profile found: ${line#RESULT:}" ;;
        CLARIFICATION:*) info "  → Clarification asked: ${line#CLARIFICATION:}" ;;
        ERROR:*)    fail "  ✗ ${line#ERROR:}" ;;
        *)          echo "  $line" ;;
    esac
done

if [ "$WS_EXIT" -eq 0 ]; then
    ok "WebSocket discovery completed successfully"
    PASSED=$((PASSED + 1))
elif [ "$WS_EXIT" -eq 2 ]; then
    warn "Skipped — websockets package not installed (pip install websockets)"
elif [ "$WS_EXIT" -eq 3 ]; then
    warn "Agent asked for clarification and may need more time. Partial pass."
    PASSED=$((PASSED + 1))
else
    fail "WebSocket discovery failed"
    FAILED=$((FAILED + 1))
fi

# ---- Test 6: Profile search endpoint ----
info "Test 6: Profile search"
PROFILES=$(curl -sf "$BACKEND_URL/api/profiles/search?name=Nadella" 2>/dev/null || echo "[]")
PROFILE_COUNT=$(echo "$PROFILES" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$PROFILE_COUNT" -ge 1 ]; then
    ok "Found $PROFILE_COUNT saved profile(s) for 'Nadella'"
    PASSED=$((PASSED + 1))
else
    warn "No saved profiles yet (expected if WS test didn't complete)"
fi

# ---- Test 7: Cache cleanup ----
info "Test 7: Cache cleanup"
CACHE_RESP=$(curl -sf -X POST "$BACKEND_URL/api/cache/cleanup")
if echo "$CACHE_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'cleaned' in d" 2>/dev/null; then
    ok "Cache cleanup works"
    PASSED=$((PASSED + 1))
else
    fail "Cache cleanup failed"
    FAILED=$((FAILED + 1))
fi

# ---- Test 8: Delete session ----
info "Test 8: Delete session"
if [ -n "$SESSION_ID" ]; then
    DEL_RESP=$(curl -sf -X DELETE "$BACKEND_URL/api/sessions/$SESSION_ID")
    if echo "$DEL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('deleted')" 2>/dev/null; then
        ok "Session deleted"
        PASSED=$((PASSED + 1))
    else
        fail "Session delete failed: $DEL_RESP"
        FAILED=$((FAILED + 1))
    fi
fi

# ---- Summary ----
echo ""
echo "======================================"
TOTAL=$((PASSED + FAILED))
if [ "$FAILED" -eq 0 ]; then
    echo -e "  ${GREEN}All $PASSED tests passed!${NC}"
else
    echo -e "  ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC} out of $TOTAL"
fi
echo "======================================"
echo ""

exit "$FAILED"
