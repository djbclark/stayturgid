#!/bin/bash
set -euo pipefail

find device/autojs6 tests/js just/tools docs/research -name "*.js" -not -path "*/node_modules/*" 2>/dev/null | while read -r f; do
  if ! grep -q "^// @generated" "$f"; then
    if head -n 1 "$f" | grep -q "^#!"; then
      sed -i.bak '1a\
// @generated
' "$f" && rm -f "$f.bak"
    else
      sed -i.bak '1s/^/\/\/ @generated\n/' "$f" && rm -f "$f.bak"
    fi
  fi
done
