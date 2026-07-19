# Site-contract CLI surfaces (docs/architecture/site-contract.md §2 / §5).
#
# Usage:
#   just site-init sitename=<name> [dir=<path>] [map=<site-map.yml>] [mode=apply|dry-run|docs]
#   just site-sync [dir=<path>] [mode=apply|dry-run|docs] [force-generated=1]
#   just site-serverapps [dir=<path>] [apps=<csv>] [mode=apply|dry-run] [force-generated=1]
#   just site-contract-check
#
# Recipes are thin wrappers: named KEY=VALUE tokens are forwarded to the
# Python entry points. mode defaults to apply inside Python when omitted.
# Prefers the project test venv (has Jinja2/PyYAML via ansible-core) when present.

# Fail closed if SITE-CONTRACT.md and literate C1 templates drift (Entangled parity)
# or if generator-owned registry seeds are stale.
site-contract-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ repo }}"
    if [[ -n "${SITE_INIT_PYTHON:-}" ]]; then
      py="${SITE_INIT_PYTHON}"
    elif [[ -x "{{ repo }}/.venv-test/bin/python" ]]; then
      py="{{ repo }}/.venv-test/bin/python"
    else
      py="python3"
    fi
    "$py" -m control.site_contract.check_entangled
    "$py" -m control.site_contract.generate_registry_seeds --check

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

# Re-render product-owned files under generated/<product>/ (apply | dry-run | docs).
site-sync *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ repo }}"
    if [[ -n "${SITE_SYNC_PYTHON:-}" ]]; then
      py="${SITE_SYNC_PYTHON}"
    elif [[ -n "${SITE_INIT_PYTHON:-}" ]]; then
      py="${SITE_INIT_PYTHON}"
    elif [[ -x "{{ repo }}/.venv-test/bin/python" ]]; then
      py="{{ repo }}/.venv-test/bin/python"
    else
      py="python3"
    fi
    exec "$py" -m control.site_contract.site_sync {{ args }}

# Activate serverapp adapters (own / inject / off) for a site overlay.
site-serverapps *args:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ repo }}"
    if [[ -n "${SITE_SERVERAPPS_PYTHON:-}" ]]; then
      py="${SITE_SERVERAPPS_PYTHON}"
    elif [[ -n "${SITE_SYNC_PYTHON:-}" ]]; then
      py="${SITE_SYNC_PYTHON}"
    elif [[ -n "${SITE_INIT_PYTHON:-}" ]]; then
      py="${SITE_INIT_PYTHON}"
    elif [[ -x "{{ repo }}/.venv-test/bin/python" ]]; then
      py="{{ repo }}/.venv-test/bin/python"
    else
      py="python3"
    fi
    exec "$py" -m control.site_contract.serverapps {{ args }}
