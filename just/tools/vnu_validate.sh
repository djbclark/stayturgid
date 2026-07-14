#!/usr/bin/env bash
# VNU (Nu HTML Checker) wrapper: validates rendered pages on the running dashboard.
set -euo pipefail

VNU_JAR="node_modules/vnu-jar/build/dist/vnu.jar"
if [ ! -f "$VNU_JAR" ]; then
  echo "vnu.jar not found — skipped (bun install vnu-jar)"
  exit 0
fi

if ! command -v java >/dev/null; then
  echo "vnu — SKIP (requires Java)"
  exit 0
fi

if ! curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then
  echo "vnu — SKIP (dashboard not running on :4097)"
  exit 0
fi

rc=0
for url in http://127.0.0.1:4097/ http://127.0.0.1:4097/errors; do
  errors=$(java -jar "$VNU_JAR" --errors-only "$url" 2>&1 | grep 'error:' | grep -v 'Attribute "hx-' || true)
  if [ -n "$errors" ]; then
    echo "FAIL: $url"
    echo "$errors"
    rc=1
  else
    echo "  OK: $url"
  fi
done

exit "$rc"
