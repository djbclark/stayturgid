# CFEngine Build project commands. Policy logic remains in device/termux/cfengine.

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
# Usage: [hosts="p7a s24"] just cf-run
cf-run:
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "{{ hosts }}" ]]; then
      python3 "{{ repo }}/control/bin/cf_run.py"
    else
      # shellcheck disable=SC2086
      python3 "{{ repo }}/control/bin/cf_run.py" {{ hosts }}
    fi
