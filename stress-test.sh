#!/bin/bash
# stress-test.sh — Simulate Drew's real workflow
# Runs N batches of M thumbnails each, back-to-back
# Tests: SSE streaming completes, images actually generated, no crashes
#
# Usage: ./stress-test.sh [batches] [concepts_per_batch] [models]
# Example: ./stress-test.sh 5 10 gemini,flux
# Default: 3 batches of 5 concepts with gemini (cheapest/fastest)

BASE="http://localhost:5050"
BATCHES=${1:-3}
CONCEPTS=${2:-5}
MODELS=${3:-"gemini"}
TIMEOUT=180  # seconds per batch

PASS=0
FAIL=0
TOTAL_IMAGES=0
TOTAL_ERRORS=0
START_TIME=$(date +%s)

ok() { echo "  ✓ $1"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL+1)); }

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  THUMBNAIL GENERATOR STRESS TEST                        ║"
echo "║  Batches: $BATCHES × $CONCEPTS concepts × models: $MODELS"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Pre-flight checks
echo "=== Pre-flight ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/" 2>/dev/null)
if [ "$STATUS" != "200" ]; then
    fail "Server not running (got $STATUS)"
    echo "FATAL: Start with: cd thumbnail_generator_v2 && venv/bin/python app.py"
    exit 1
fi
ok "Server running"

HEALTH=$(curl -s "$BASE/api/health" 2>/dev/null)
if echo "$HEALTH" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    ok "Health endpoint returns valid JSON"
else
    fail "Health endpoint broken"
fi

MODEL_LIST=$(curl -s "$BASE/api/models" 2>/dev/null)
AVAILABLE=$(echo "$MODEL_LIST" | python3 -c "
import sys, json
models = json.load(sys.stdin)['models']
print(','.join(m['id'] for m in models))
" 2>/dev/null)
echo "  Available models: $AVAILABLE"

# Check requested models are available
for m in $(echo "$MODELS" | tr ',' ' '); do
    if echo "$AVAILABLE" | grep -q "$m"; then
        ok "Model '$m' available"
    else
        fail "Model '$m' NOT available"
    fi
done

# Video titles to cycle through (realistic Species content)
TITLES=(
    "Why This Deep Sea Creature Shouldn't Exist"
    "The Most Dangerous Parasite You've Never Heard Of"
    "Scientists Just Found a New Species in Your Backyard"
    "This Animal Can Survive in Space — Here's How"
    "The Extinction Event Nobody Is Talking About"
    "Why Octopuses Are Basically Aliens"
    "This Fungus Controls Minds — And It's Spreading"
    "The Fish That Walks on Land Is Taking Over"
    "We Were Wrong About Dinosaur Colors"
    "The Deadliest Venom on Earth Might Save Your Life"
    "This Bird Hasn't Evolved in 60 Million Years"
    "Why Sharks Are Older Than Trees"
    "The Insect That Builds Cities Bigger Than Manhattan"
    "This Snake Can Fly — And It's Coming North"
    "The Animal That Literally Cannot Die"
    "Why Crows Are Smarter Than You Think"
    "The Deep Ocean Discovery That Changed Everything"
    "This Parasite Turns Snails Into Zombies"
    "The World's Smallest Predator Is Terrifying"
    "Why This Jellyfish Breaks the Rules of Biology"
)

echo ""
echo "=== Running $BATCHES batches ==="

for batch in $(seq 1 $BATCHES); do
    # Pick a random title
    TITLE_IDX=$(( (batch - 1) % ${#TITLES[@]} ))
    TITLE="${TITLES[$TITLE_IDX]}"

    echo ""
    echo "--- Batch $batch/$BATCHES: \"$TITLE\" ($CONCEPTS concepts × $MODELS) ---"
    BATCH_START=$(date +%s)

    # URL-encode the title (pipe to avoid shell quoting issues)
    ENCODED_TITLE=$(echo "$TITLE" | python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read().strip()))")

    # Stream the SSE response, collect results
    BATCH_LOG="/tmp/thumb-stress-batch-${batch}.log"
    BATCH_IMAGES=0
    BATCH_ERRORS=0
    GOT_CONCEPTS=false
    GOT_COMPLETE=false
    SSE_TIMEOUT=false

    # Use curl with timeout to stream SSE
    curl -s -N -m "$TIMEOUT" \
        "$BASE/api/parallel-generate?titles=${ENCODED_TITLE}&count=${CONCEPTS}&models=${MODELS}&use_favorites=false" \
        > "$BATCH_LOG" 2>&1 &
    CURL_PID=$!

    # Wait for curl to finish (or timeout)
    wait $CURL_PID 2>/dev/null
    CURL_EXIT=$?

    if [ $CURL_EXIT -eq 28 ]; then
        SSE_TIMEOUT=true
        fail "Batch $batch TIMED OUT after ${TIMEOUT}s"
    fi

    # Parse SSE results
    if [ -f "$BATCH_LOG" ]; then
        # Count image results
        BATCH_IMAGES=$(grep -c '"type": *"thumbnail"' "$BATCH_LOG" 2>/dev/null || true)
        [ -z "$BATCH_IMAGES" ] && BATCH_IMAGES=0
        # Also check for model_thumbnail type
        BATCH_IMAGES2=$(grep -c '"type": *"model_thumbnail"' "$BATCH_LOG" 2>/dev/null || true)
        [ -z "$BATCH_IMAGES2" ] && BATCH_IMAGES2=0
        BATCH_IMAGES=$((BATCH_IMAGES + BATCH_IMAGES2))

        # Check for concepts phase
        if grep -q '"type": *"concepts"' "$BATCH_LOG" 2>/dev/null || grep -q '"type": *"progress".*concepts' "$BATCH_LOG" 2>/dev/null; then
            GOT_CONCEPTS=true
        fi

        # Check for completion
        if grep -q '"type": *"complete"' "$BATCH_LOG" 2>/dev/null || grep -q '"type": *"done"' "$BATCH_LOG" 2>/dev/null; then
            GOT_COMPLETE=true
        fi

        # Count errors
        BATCH_ERRORS=$(grep -c '"type": *"error"' "$BATCH_LOG" 2>/dev/null || true)
        [ -z "$BATCH_ERRORS" ] && BATCH_ERRORS=0
        # Also count model-level errors
        MODEL_ERRORS=$(grep -c '"type": *"model_error"' "$BATCH_LOG" 2>/dev/null || true)
        [ -z "$MODEL_ERRORS" ] && MODEL_ERRORS=0
        BATCH_ERRORS=$((BATCH_ERRORS + MODEL_ERRORS))
    fi

    BATCH_END=$(date +%s)
    BATCH_DURATION=$((BATCH_END - BATCH_START))

    # Report batch results
    echo "  Duration: ${BATCH_DURATION}s"
    echo "  Images generated: $BATCH_IMAGES"
    echo "  Errors: $BATCH_ERRORS"

    if [ "$SSE_TIMEOUT" = true ]; then
        TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
    elif [ "$BATCH_IMAGES" -gt 0 ]; then
        ok "Batch $batch: $BATCH_IMAGES images in ${BATCH_DURATION}s"
        TOTAL_IMAGES=$((TOTAL_IMAGES + BATCH_IMAGES))
    else
        fail "Batch $batch: 0 images generated"
        # Show last few lines of log for debugging
        echo "  Last 5 SSE messages:"
        grep "^data:" "$BATCH_LOG" 2>/dev/null | tail -5 | while read -r line; do
            echo "    $line"
        done
    fi

    if [ "$BATCH_ERRORS" -gt 0 ]; then
        TOTAL_ERRORS=$((TOTAL_ERRORS + BATCH_ERRORS))
        echo "  Error details:"
        grep '"type": *"error"\|"type": *"model_error"' "$BATCH_LOG" 2>/dev/null | head -3 | while read -r line; do
            echo "    $line"
        done
    fi

    # Brief pause between batches (simulate user tweaking prompts)
    if [ "$batch" -lt "$BATCHES" ]; then
        echo "  (2s pause before next batch...)"
        sleep 2
    fi
done

# Check server is still alive after all batches
echo ""
echo "=== Post-stress check ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/" 2>/dev/null)
if [ "$STATUS" = "200" ]; then
    ok "Server still running after $BATCHES batches"
else
    fail "SERVER CRASHED during stress test"
fi

# Check history was saved
HISTORY=$(curl -s "$BASE/api/history" 2>/dev/null)
if echo "$HISTORY" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    ok "History endpoint still returns valid JSON"
else
    fail "History endpoint broken after stress test"
fi

# Final report
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  RESULTS                                                 ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Batches:     $BATCHES                                  "
echo "║  Total images: $TOTAL_IMAGES                            "
echo "║  Total errors: $TOTAL_ERRORS                            "
echo "║  Duration:    ${TOTAL_DURATION}s                        "
echo "║  Passed:      $PASS checks                              "
echo "║  Failed:      $FAIL checks                              "
echo "╚══════════════════════════════════════════════════════════╝"

if [ "$FAIL" -eq 0 ] && [ "$TOTAL_IMAGES" -gt 0 ]; then
    echo ""
    echo "ALL CLEAR — survived $BATCHES batches with $TOTAL_IMAGES images, 0 failures."
    echo "Confidence: HIGH for Drew's workflow."
elif [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "ISSUES FOUND — $FAIL failures across $BATCHES batches."
    echo "Fix these before sending Drew to generate at scale."
fi

# Cleanup
rm -f /tmp/thumb-stress-batch-*.log

exit $FAIL
