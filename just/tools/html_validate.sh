#!/usr/bin/env bash
set -euo pipefail

if [ ! -d node_modules ]; then
  echo "node_modules not found (run bun install) — skipped"
  exit 0
fi

tmpd="$(mktemp -d)"
trap 'rm -rf "$tmpd"' EXIT

ok=0
for f in $(git ls-files '*.html'); do
  python3 just/tools/html_strip_jinja.py "$f" >"$tmpd/$(basename "$f")" 2>/dev/null
  if ! bunx html-validate --config .html-validate.json "$tmpd/$(basename "$f")" >/dev/null 2>&1; then
    errors=$(bunx html-validate --config .html-validate.json "$tmpd/$(basename "$f")" 2>&1 | grep -c 'error' || true)
    if [ "$errors" -gt 0 ]; then
      echo "FAIL: $f ($errors errors)"
      ok=1
    fi
  fi
done

if [ "$ok" -ne 0 ]; then
  echo "html-validate: some files failed"
  exit 1
fi

echo "html-validate: all passed"
