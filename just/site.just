# Site-contract CLI surfaces (docs/architecture/site-contract.md §2).
#
# Usage:
#   just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
#
# The recipe is a thin wrapper: named KEY=VALUE tokens are forwarded to the
# Python entry point. mode defaults to apply inside Python when omitted.

# Initialize a private site overlay (apply | dry-run | docs).
site-init *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ {{ if args == "" { "1" } else { "0" } }} -eq 1 ]]; then
      echo "usage: just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]" >&2
      exit 1
    fi
    cd "{{ repo }}"
    python3 -m control.site_contract.site_init {{ args }}
