#!/usr/bin/env bash
set -euo pipefail

if [ ! -d node_modules ]; then
  echo "pa11y not available — skipped"
  exit 0
fi

if ! curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then
  echo "pa11y — SKIP (dashboard not running on :4097)"
  exit 0
fi

# Use Chromium from our Puppeteer (pa11y's own bundled one may have stale/corrupted Chrome)
chrome=$(find $HOME/.cache/puppeteer/chrome -name "Google Chrome for Testing" -type f 2>/dev/null | head -1)
if [ -n "$chrome" ] && [ -x "$chrome" ]; then
  export PUPPETEER_EXECUTABLE_PATH="$chrome"
fi

rc=0
for url in http://127.0.0.1:4097/ http://127.0.0.1:4097/errors; do
  echo "  $url"
  set +e
  output=$(PUPPETEER_EXECUTABLE_PATH="${PUPPETEER_EXECUTABLE_PATH:-}" bunx pa11y --config .pa11yci.json "$url" 2>&1)
  pa11y_rc=$?
  set -e
  echo "$output" | grep -vE '(Welcome to Pa11y|Running Pa11y|Results for|No issues found|^$)' || true
  if [ "$pa11y_rc" -eq 2 ]; then
    echo "  → a11y issues found (exit 2)"
  elif [ "$pa11y_rc" -ne 0 ]; then
    echo "  → pa11y error"
    rc=1
  fi
done

exit "$rc"
