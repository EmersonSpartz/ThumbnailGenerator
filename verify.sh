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

# 8. Review page content check — catches missing pairs, broken filters, broken images
#    This exists because 3 bugs in a row went undetected: API not scanning comparison.json,
#    JS filter excluding new experiment types, and broken image paths from filename truncation.
echo -n "  GET /review... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:5050/review" 2>/dev/null)
if [ "$STATUS" = "200" ]; then
    echo "OK ($STATUS)"
else
    echo "FAIL ($STATUS)"
    FAIL=1
fi

echo -n "  Review API returns results... "
RESULT_COUNT=$(curl -s http://localhost:5050/api/experiment-results 2>/dev/null | python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data) if isinstance(data,list) else len(data.get('results',[])))" 2>/dev/null)
if [ "$RESULT_COUNT" -gt 0 ] 2>/dev/null; then
    echo "OK ($RESULT_COUNT pairs)"
else
    echo "WARN (0 pairs — expected if no experiments run yet)"
fi

echo -n "  Review image paths valid... "
BROKEN=$(curl -s http://localhost:5050/api/experiment-results 2>/dev/null | python3 -c "
import json, sys, os
data = json.load(sys.stdin)
results = data if isinstance(data, list) else data.get('results', [])
broken = 0
checked = 0
for r in results[-20:]:  # Check last 20 pairs
    for key in ['iter1_path_rel', 'iter2_path_rel']:
        rel = r.get(key, '')
        if rel:
            checked += 1
            full = os.path.join('output', rel)
            if not os.path.exists(full):
                broken += 1
print(f'{broken}/{checked}')
" 2>/dev/null)
BROKEN_COUNT=$(echo "$BROKEN" | cut -d/ -f1)
CHECKED_COUNT=$(echo "$BROKEN" | cut -d/ -f2)
if [ "$BROKEN_COUNT" = "0" ] 2>/dev/null; then
    echo "OK ($CHECKED_COUNT checked, 0 broken)"
elif [ "$CHECKED_COUNT" = "0" ] 2>/dev/null; then
    echo "OK (no pairs to check)"
else
    echo "FAIL ($BROKEN_COUNT/$CHECKED_COUNT images have broken paths)"
    FAIL=1
fi

# DOM health check — catches "page loads but is broken" class of bugs
# This runs via curl + grep, no browser needed. Catches:
#   - Blank page (JS crash killed rendering)
#   - Missing critical UI elements (buttons, tabs, forms)
#   - Missing script tags (build broke)
#   - Inline error messages visible in HTML
echo ""
echo "--- DOM Health Check ---"
PAGE_HTML=$(curl -s "http://localhost:5050/" 2>/dev/null)
PAGE_LEN=${#PAGE_HTML}

echo -n "  Page not blank... "
if [ "$PAGE_LEN" -gt 500 ]; then
    echo "OK ($PAGE_LEN chars)"
else
    echo "FAIL (only $PAGE_LEN chars — page is blank or errored)"
    FAIL=1
fi

# Check for critical UI elements that MUST exist in the rendered HTML
# These are Jinja-rendered, so they're in the curl output (no JS hydration needed)
MISSING_ELEMENTS=""
for element in \
    'id="generate-btn"' \
    'id="thumbnail-grid"' \
    'id="history-grid"' \
    'id="favorites-grid"' \
    'id="video-select"' \
    'class="tab-btn"' \
    'id="smart-enhance"' \
    '__runQA'; do
    if ! echo "$PAGE_HTML" | grep -q "$element"; then
        MISSING_ELEMENTS="$MISSING_ELEMENTS $element"
    fi
done

echo -n "  Critical UI elements... "
if [ -z "$MISSING_ELEMENTS" ]; then
    echo "OK (all present)"
else
    echo "FAIL (missing:$MISSING_ELEMENTS)"
    FAIL=1
fi

# Check that no obvious error indicators appear in the HTML
echo -n "  No error indicators... "
ERROR_INDICATORS=""
for indicator in "Internal Server Error" "Traceback (most recent" "SyntaxError" "TypeError:" "ReferenceError:" "500 Internal"; do
    if echo "$PAGE_HTML" | grep -qi "$indicator"; then
        ERROR_INDICATORS="$ERROR_INDICATORS '$indicator'"
    fi
done
if [ -z "$ERROR_INDICATORS" ]; then
    echo "OK"
else
    echo "FAIL (found:$ERROR_INDICATORS)"
    FAIL=1
fi

# Check deployed version if DEPLOY_URL is set (catches localhost-ok-but-deployed-broken)
DEPLOY_URL="${DEPLOY_URL:-}"
if [ -n "$DEPLOY_URL" ]; then
    echo ""
    echo "--- Deployed Version Check ($DEPLOY_URL) ---"
    DEPLOY_HTML=$(curl -s -m 15 "$DEPLOY_URL/" 2>/dev/null)
    DEPLOY_LEN=${#DEPLOY_HTML}
    echo -n "  Deployed page not blank... "
    if [ "$DEPLOY_LEN" -gt 500 ]; then
        echo "OK ($DEPLOY_LEN chars)"
    else
        echo "FAIL (only $DEPLOY_LEN chars — deployed page is blank or unreachable)"
        FAIL=1
    fi

    echo -n "  Deployed critical elements... "
    DEPLOY_MISSING=""
    for element in 'id="generate-btn"' 'id="thumbnail-grid"' '__runQA'; do
        if ! echo "$DEPLOY_HTML" | grep -q "$element"; then
            DEPLOY_MISSING="$DEPLOY_MISSING $element"
        fi
    done
    if [ -z "$DEPLOY_MISSING" ]; then
        echo "OK"
    else
        echo "FAIL (missing:$DEPLOY_MISSING)"
        FAIL=1
    fi
fi

# 9. Post-deploy user flow test — runs only when RAILWAY_QA=true
#    Tests actual user flows against the live Railway URL.
#    Usage: RAILWAY_QA=true ./verify.sh
if [ "${RAILWAY_QA:-false}" = "true" ]; then
    echo ""
    echo "--- Railway QA Flow (RAILWAY_QA=true) ---"
    if [ -x "$(dirname "$0")/qa-deploy.sh" ]; then
        "$(dirname "$0")/qa-deploy.sh"
        QA_RESULT=$?
        if [ $QA_RESULT -ne 0 ]; then
            echo "FAIL: Railway QA flow failed"
            FAIL=1
        fi
    else
        echo "WARNING: qa-deploy.sh not found or not executable — skipping Railway QA"
    fi
fi

# 10. Kill server if we started it
if [ "$SERVER_RUNNING" = false ] && [ -n "$SERVER_PID" ]; then
    kill $SERVER_PID 2>/dev/null || true
    echo "Stopped test server"
fi

if [ $FAIL -eq 1 ]; then
    echo "=== VERIFY FAILED ==="
    exit 1
fi

echo "=== ALL CHECKS PASSED ==="
