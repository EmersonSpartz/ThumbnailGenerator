#!/usr/bin/env bash
set -euo pipefail

RAILWAY_URL="https://thumbnail-generator-v2-production.up.railway.app"
FORCE=false

if [[ "${1:-}" == "--force" ]]; then
    FORCE=true
fi

echo "=== Thumbnail Generator Deploy Guard ==="
echo ""

# Check for active jobs
echo "Checking for active generation jobs..."
RESPONSE=$(curl -s -w "\n%{http_code}" --max-time 10 "$RAILWAY_URL/api/jobs/active" 2>/dev/null || echo -e "\n000")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$HTTP_CODE" == "200" ]]; then
    # Parse running jobs count
    RUNNING=$(echo "$BODY" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    jobs = data if isinstance(data, list) else data.get('jobs', data.get('active', []))
    if isinstance(jobs, list):
        running = [j for j in jobs if j.get('status') == 'running']
        print(len(running))
    elif isinstance(data, dict) and 'count' in data:
        print(data['count'])
    else:
        print(0)
except:
    print(0)
" 2>/dev/null || echo "0")

    if [[ "$RUNNING" -gt 0 ]]; then
        echo "WARNING: $RUNNING active generation job(s) detected!"
        echo "Deploying will restart the server and kill in-progress work."
        echo ""
        if [[ "$FORCE" == true ]]; then
            echo "--force flag set, proceeding anyway."
        else
            read -rp "Deploy anyway? (y/N) " confirm
            if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
                echo "Deploy cancelled."
                exit 1
            fi
        fi
    else
        echo "No active jobs found. Safe to deploy."
    fi
elif [[ "$HTTP_CODE" == "401" || "$HTTP_CODE" == "403" ]]; then
    echo "WARNING: Could not verify active jobs (auth required: HTTP $HTTP_CODE)."
    echo "Proceeding with deploy — check manually if unsure."
elif [[ "$HTTP_CODE" == "000" ]]; then
    echo "WARNING: Could not reach the app (timeout or connection error)."
    echo "App may already be down. Proceeding with deploy."
else
    echo "WARNING: Could not verify active jobs (HTTP $HTTP_CODE)."
    echo "Proceeding with deploy."
fi

echo ""
echo "Deploying to Railway..."
railway up --detach

echo ""
echo "Waiting for deploy to become healthy..."
HEALTHY=false
for i in $(seq 1 12); do
    sleep 10
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$RAILWAY_URL/health" 2>/dev/null || echo "000")
    if [[ "$STATUS" == "200" ]]; then
        HEALTHY=true
        echo "Deploy healthy after $((i * 10))s."
        break
    else
        echo "  Attempt $i/12: /health returned $STATUS, retrying in 10s..."
    fi
done

if [[ "$HEALTHY" == false ]]; then
    echo "ERROR: Deploy did not become healthy within 120s!"
    echo "Check Railway dashboard: https://railway.app"
    exit 1
fi

echo ""
echo "Deploy complete."
