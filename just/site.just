# Site-contract CLI surfaces (docs/architecture/site-contract.md §2).
#
# Usage:
#   just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
#
# The recipe is a thin wrapper: named KEY=VALUE tokens are forwarded to the
# Python entry point. mode defaults to apply inside Python when omitted.
# Prefers the project test venv (has Jinja2 via ansible-core) when present.

# Initialize a private site overlay (apply | dry-run | docs).
site-init *args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ {{ if args == "" { "1" } else { "0" } }} -eq 1 ]]; then
      echo "usage: just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]" >&2
      exit 1
    fi
    cd "{{ repo }}"
    if [[ -n "${SITE_INIT_PYTHON:-}" ]]; then
      py="${SITE_INIT_PYTHON}"
    elif [[ -x "{{ repo }}/.venv-test/bin/python" ]]; then
      py="{{ repo }}/.venv-test/bin/python"
    else
      py="python3"
    fi
    exec "$py" -m control.site_contract.site_init {{ args }}
