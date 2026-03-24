#!/bin/bash
# Standalone visual render check for post-deploy verification.
# Runs headless Chrome to verify the page actually renders thumbnail cards.
#
# Usage:
#   ./check-render.sh [URL]
#
# Examples:
#   ./check-render.sh                                          # uses default Railway URL
#   ./check-render.sh https://web-production-d277.up.railway.app  # explicit URL

cd "$(dirname "$0")"

URL="${1:-}"
EXTRA_ARGS=""
if [ -n "$URL" ]; then
    EXTRA_ARGS="$URL"
fi

echo "=== Visual Render Check ==="
echo ""

if ! command -v node &> /dev/null; then
    echo "ERROR: node not found. Install Node.js first."
    exit 1
fi

if [ ! -d "node_modules/puppeteer" ]; then
    echo "ERROR: puppeteer not installed. Run: npm install puppeteer"
    exit 1
fi

node visual-check.js $EXTRA_ARGS
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "Page renders correctly"
else
    echo "RENDERING BROKEN"
    echo "Debug screenshot: /tmp/visual-check.png"
    echo "Open it:  open /tmp/visual-check.png"
    exit 1
fi
