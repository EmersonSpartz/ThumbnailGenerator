#!/bin/bash
# Post-deploy QA runner for Thumbnail Generator.
# Waits for Railway to come up, then runs the full user-flow test.
#
# Usage:
#   ./qa-deploy.sh [RAILWAY_URL]
#
# Env vars:
#   QA_BASE_URL   - override the default Railway URL (also accepted as $1)
#   QA_PASSWORD   - app password if auth is enabled
#
# Exit codes:
#   0 - all tests passed
#   1 - tests failed or Railway never came up

set -euo pipefail
cd "$(dirname "$0")"

BASE_URL="${1:-${QA_BASE_URL:-https://web-production-d277.up.railway.app}}"
HEALTH_URL="${BASE_URL}/health"
WAIT_SECS=180   # max 3 minutes
POLL_INTERVAL=5

echo ""
echo "=== qa-deploy.sh ==="
echo "Target: $BASE_URL"
echo ""

# ------------------------------------------------------------------
# 1. Wait for Railway to respond
# ------------------------------------------------------------------
echo "Waiting for Railway to come up (up to ${WAIT_SECS}s)..."
START_TIME=$(date +%s)
READY=false

while true; do
  NOW=$(date +%s)
  ELAPSED=$(( NOW - START_TIME ))

  if [ $ELAPSED -ge $WAIT_SECS ]; then
    echo "FAIL: Railway did not come up within ${WAIT_SECS}s"
    exit 1
  fi

  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "000")
  if [ "$HTTP_STATUS" = "200" ]; then
    READY=true
    echo "Railway is up (${ELAPSED}s elapsed)"
    break
  fi

  echo "  [${ELAPSED}s] /health returned ${HTTP_STATUS}, retrying in ${POLL_INTERVAL}s..."
  sleep $POLL_INTERVAL
done

echo ""

# ------------------------------------------------------------------
# 2. Run node qa-flow.js
# ------------------------------------------------------------------
export QA_BASE_URL="$BASE_URL"

if ! command -v node &>/dev/null; then
  echo "FAIL: node not found in PATH"
  exit 1
fi

node qa-flow.js "$BASE_URL"
QA_EXIT=$?

echo ""
if [ $QA_EXIT -eq 0 ]; then
  echo "=== QA PASSED ==="
else
  echo "=== QA FAILED ==="
fi

exit $QA_EXIT
