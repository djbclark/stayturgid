# CFEngine Build project commands. Policy logic remains in device/termux/cfengine.

# Pin the Mac control-node CFEngine to 3.27.1 to match the Termux fleet, and
# stop brew upgrade from bumping it. Idempotent. See packaging/homebrew/README.md.
cfengine-pin:
    #!/usr/bin/env bash
    set -euo pipefail
    tap="cfengine-local/cfengine"
    brew tap-new "$tap" >/dev/null 2>&1 || true
    cp "{{ repo }}/packaging/homebrew/cfengine@3.27.1.rb" "$(brew --repo "$tap")/Formula/"
    if ! brew list --versions cfengine@3.27.1 >/dev/null 2>&1; then
      brew install "$tap/cfengine@3.27.1"
    fi
    brew uninstall --ignore-dependencies cfengine >/dev/null 2>&1 || true
    brew link --overwrite cfengine@3.27.1 >/dev/null 2>&1 || true
    brew pin cfengine@3.27.1 >/dev/null 2>&1 || true
    echo "pinned: $(brew list --pinned | grep cfengine || echo NONE)"
    cf-runagent --version | head -1

cfbs-validate:
    cd device/termux/cfengine && cfbs validate
    cf-promises -f "{{ repo }}/device/termux/cfengine/policy/stayturgid.cf"
    cf-promises -f "{{ repo }}/device/termux/cfengine/policy/cf-serverd.cf"

cfbs-build: cfbs-validate
    cd device/termux/cfengine && cfbs build
    diff -r --exclude=cfbs.json device/termux/cfengine/policy device/termux/cfengine/out/masterfiles

# Run CFEngine repair bundles on inventory-derived SSH aliases.  Default
# targeting excludes hosts marked stayturgid_fleet_status: offline; naming a
# host explicitly remains the operator override (matching deploy_fleet.py).
# Usage: just cf-run [hosts="p7a s24"]
cf-run:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "{{ hosts }}" ]]; then
      python3 "{{ repo }}/control/bin/cf_run.py"
    else
      # shellcheck disable=SC2086
      python3 "{{ repo }}/control/bin/cf_run.py" {{ hosts }}
    fi
