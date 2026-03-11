#!/bin/bash
# Deep verification — tests actual generation flows, not just server startup
# Takes ~2-3 minutes (makes real API calls). Run before declaring "done".
# verify.sh is the fast check (5s). This is the thorough check.

set -uo pipefail
cd "$(dirname "$0")"

PASS=0
FAIL=0
WARN=0

pass() { echo "  PASS: $1"; ((PASS++)); }
fail() { echo "  FAIL: $1"; ((FAIL++)); }
warn() { echo "  WARN: $1"; ((WARN++)); }

echo "=== Deep Verify: Thumbnail Generator ==="
echo ""

# Ensure server is running
if ! curl -s http://localhost:5050/api/health > /dev/null 2>&1; then
    echo "Starting server..."
    venv/bin/python app.py > /tmp/flask_deep_verify.log 2>&1 &
    SERVER_PID=$!
    for i in $(seq 1 20); do
        curl -s http://localhost:5050/ > /dev/null 2>&1 && break
        sleep 0.5
    done
    if ! curl -s http://localhost:5050/ > /dev/null 2>&1; then
        echo "FAIL: Server didn't start"
        cat /tmp/flask_deep_verify.log
        exit 1
    fi
    STARTED_SERVER=true
else
    STARTED_SERVER=false
fi

echo "── 1. Quick-generate with each model ──"
for model in gemini nanobanana2 flux sdxl recraft midjourney; do
    RESULT=$(curl -s -m 90 -X POST http://localhost:5050/api/quick-generate \
      -H "Content-Type: application/json" \
      -d "{\"prompt\": \"A dramatic close-up of a deep sea creature, bioluminescent\", \"model\": \"$model\"}" 2>&1)
    SUCCESS=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('success',False))" 2>/dev/null)
    if [ "$SUCCESS" = "True" ]; then
        pass "$model generates images"
    else
        ERROR=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error','unknown')[:80])" 2>/dev/null)
        # Rate limits are warnings, not failures
        if echo "$ERROR" | grep -qi "rate_limit\|429\|quota"; then
            warn "$model rate-limited: $ERROR"
        else
            fail "$model: $ERROR"
        fi
    fi
done
echo ""

echo "── 2. Model Shootout (SSE streaming) ──"
SHOOTOUT_EVENTS=$(curl -s -m 90 "http://localhost:5050/api/model-shootout?titles=test+video&models=gemini&count=1" 2>&1 | grep "^data:" | python3 -c "
import json, sys
types = []
for line in sys.stdin:
    try: types.append(json.loads(line.strip().replace('data: ','',1)).get('type',''))
    except: pass
print(' '.join(types))
" 2>/dev/null)
if echo "$SHOOTOUT_EVENTS" | grep -q "shootout_complete"; then
    pass "Model shootout completes"
elif echo "$SHOOTOUT_EVENTS" | grep -q "error"; then
    fail "Model shootout errored"
else
    fail "Model shootout didn't complete (events: $SHOOTOUT_EVENTS)"
fi

echo "── 3. Parallel Generate ──"
PARALLEL_EVENTS=$(curl -s -m 120 "http://localhost:5050/api/parallel-generate?titles=test+video&models=gemini&count=1" 2>&1 | grep "^data:" | python3 -c "
import json, sys
types = set()
for line in sys.stdin:
    try: types.add(json.loads(line.strip().replace('data: ','',1)).get('type',''))
    except: pass
print(' '.join(sorted(types)))
" 2>/dev/null)
if echo "$PARALLEL_EVENTS" | grep -q "parallel_complete"; then
    pass "Parallel generate completes"
    if echo "$PARALLEL_EVENTS" | grep -q "model_thumbnail"; then
        pass "Parallel generate produces thumbnails"
    else
        fail "Parallel generate completed but no thumbnails"
    fi
else
    fail "Parallel generate didn't complete (events: $PARALLEL_EVENTS)"
fi

echo "── 4. Agentic Generate ──"
AGENTIC_EVENTS=$(curl -s -m 180 "http://localhost:5050/api/agentic-generate?titles=test+video&models=gemini&count=1&max_iterations=1&llm=gemini" 2>&1 | grep "^data:" | python3 -c "
import json, sys
types = set()
for line in sys.stdin:
    try: types.add(json.loads(line.strip().replace('data: ','',1)).get('type',''))
    except: pass
print(' '.join(sorted(types)))
" 2>/dev/null)
if echo "$AGENTIC_EVENTS" | grep -q "agentic_complete"; then
    pass "Agentic generate completes"
    if echo "$AGENTIC_EVENTS" | grep -q "image_generated"; then
        pass "Agentic generate produces images"
    else
        fail "Agentic generate completed but no images"
    fi
else
    fail "Agentic generate didn't complete (events: $AGENTIC_EVENTS)"
fi

echo ""

# Cleanup
if [ "$STARTED_SERVER" = true ] && [ -n "${SERVER_PID:-}" ]; then
    kill $SERVER_PID 2>/dev/null || true
fi

echo "=== Results: $PASS passed, $FAIL failed, $WARN warnings ==="
if [ $FAIL -gt 0 ]; then
    echo "=== DEEP VERIFY FAILED ==="
    exit 1
fi
echo "=== DEEP VERIFY PASSED ==="
