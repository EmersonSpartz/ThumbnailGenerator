#!/bin/bash
# Quick smoke test for thumbnail generator
# Run after any code change to catch breaks before Emerson does

set -e

cd "$(dirname "$0")"

echo "=== Thumbnail Generator Verify ==="

# 1. Check Python syntax/imports (catches most breaks instantly)
echo -n "Checking imports... "
if venv/bin/python -c "from app import app" 2>/tmp/verify_err.txt; then
    echo "OK"
else
    echo "FAIL"
    cat /tmp/verify_err.txt
    exit 1
fi

# 2. Check all lib modules import cleanly
echo -n "Checking lib modules... "
if venv/bin/python -c "from lib import *" 2>/tmp/verify_err.txt; then
    echo "OK"
else
    echo "FAIL"
    cat /tmp/verify_err.txt
    exit 1
fi

# 3. Start server (if not already running) and check key endpoints
SERVER_RUNNING=false
if curl -s http://localhost:5050/ > /dev/null 2>&1; then
    SERVER_RUNNING=true
    echo "Server already running on :5050"
else
    echo -n "Starting server... "
    venv/bin/python app.py > /tmp/flask_verify.log 2>&1 &
    SERVER_PID=$!

    # Wait up to 10 seconds for server to start
    for i in $(seq 1 20); do
        if curl -s http://localhost:5050/ > /dev/null 2>&1; then
            echo "OK (PID $SERVER_PID)"
            break
        fi
        sleep 0.5
    done

    if ! curl -s http://localhost:5050/ > /dev/null 2>&1; then
        echo "FAIL - server didn't start"
        cat /tmp/flask_verify.log
        kill $SERVER_PID 2>/dev/null || true
        exit 1
    fi
fi

# 4. Check REST endpoints
FAIL=0
for endpoint in "/" "/api/health" "/api/models" "/api/get-rubric" "/api/history" "/api/favorites"; do
    echo -n "  GET $endpoint... "
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5050$endpoint" 2>/dev/null)
    if [ "$STATUS" = "200" ]; then
        echo "OK ($STATUS)"
    else
        echo "FAIL ($STATUS)"
        FAIL=1
    fi
done

# 5. Check that /api/models returns actual models (not empty)
echo -n "  Models list non-empty... "
MODEL_COUNT=$(curl -s http://localhost:5050/api/models 2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('models',[])))" 2>/dev/null)
if [ "$MODEL_COUNT" -gt 0 ] 2>/dev/null; then
    echo "OK ($MODEL_COUNT models)"
else
    echo "FAIL (no models returned)"
    FAIL=1
fi

# 6. Check SSE endpoints actually stream (connect, get first event, disconnect)
# This catches: broken streaming, missing imports, API client init failures
for sse_endpoint in \
    "/api/model-shootout?titles=test&models=gemini&count=1" \
    "/api/parallel-generate?titles=test&models=gemini&count=1"; do
    ENDPOINT_NAME=$(echo "$sse_endpoint" | sed 's/?.*//')
    echo -n "  SSE $ENDPOINT_NAME... "
    FIRST_EVENT=$(curl -s -m 30 "http://localhost:5050$sse_endpoint" 2>/dev/null | head -1)
    if echo "$FIRST_EVENT" | grep -q "^data:"; then
        EVENT_TYPE=$(echo "$FIRST_EVENT" | python3 -c "import json,sys; print(json.loads(sys.stdin.read().replace('data: ','',1)).get('type','?'))" 2>/dev/null)
        echo "OK (first event: $EVENT_TYPE)"
    else
        echo "FAIL (no SSE events)"
        FAIL=1
    fi
done

# 7. Check API keys are configured (catches missing .env)
echo -n "  API keys configured... "
KEY_CHECK=$(venv/bin/python -c "
from lib.config import Settings
s = Settings()
missing = []
if not s.anthropic_api_key: missing.append('ANTHROPIC_API_KEY')
if not s.google_api_keys: missing.append('GOOGLE_API_KEYS')
if missing: print('MISSING: ' + ', '.join(missing))
else: print('OK')
" 2>/dev/null)
if echo "$KEY_CHECK" | grep -q "^OK"; then
    echo "OK"
else
    echo "FAIL ($KEY_CHECK)"
    FAIL=1
fi

# 8. Kill server if we started it
if [ "$SERVER_RUNNING" = false ] && [ -n "$SERVER_PID" ]; then
    kill $SERVER_PID 2>/dev/null || true
    echo "Stopped test server"
fi

if [ $FAIL -eq 1 ]; then
    echo "=== VERIFY FAILED ==="
    exit 1
fi

echo "=== ALL CHECKS PASSED ==="
