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
    elif command -v python3 >/dev/null 2>&1 && python3 -c "import entangled" 2>/dev/null; then
      py="python3"
    else
      echo "### site-contract-check — SKIP (.venv-test missing — run 'just worktree-setup')"
      exit 0
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

# Upgrade a Tier-1 pinned serverapp formula and converge the running service
# onto the new binary. The serverapp_* roles deliberately never upgrade (they
# pin to prevent drift), so the version bump is an explicit operator action —
# this recipe is that action, in one place instead of tribal knowledge.
#
#   just serverapps-upgrade grafana
#   just serverapps-upgrade vector formula=vectordotdev/brew/vector
#
# site-serverapps then restarts the service (its stale-binary trigger fires)
# and asserts it is actually running the new binary before reporting success.
serverapps-upgrade app dir="" formula="":
    #!/usr/bin/env bash
    set -euo pipefail
    app="{{ app }}"
    dir="{{ dir }}"
    formula="{{ formula }}"
    [ -n "$formula" ] || formula="$app"
    echo "==> $formula: unpin"
    brew unpin "$formula" >/dev/null 2>&1 || true
    echo "==> $formula: upgrade"
    brew upgrade "$formula"
    echo "==> $formula: re-pin"
    brew pin "$formula" >/dev/null 2>&1 || true
    echo "==> $app: converge onto the new binary"
    if [ -n "$dir" ]; then
      just --justfile "{{ repo }}/justfile" site-serverapps dir="$dir" apps="$app"
    else
      just --justfile "{{ repo }}/justfile" site-serverapps apps="$app"
    fi
