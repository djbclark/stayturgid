# Fleet operations — deploy, verify, bootstrap, health, FIRERPA.

# Private implementations (prefixed with underscore) and legacy shims are provided for backward compatibility.
# Positional wrappers use `host=""` (optional positional host argument) and rely on environment variables for configuration.

# ---------- Deploy ----------
# Inner recipes declare `host=""` because nested `just` calls only forward
# arguments to recipes with matching parameters (an extra bare token is
# parsed as another recipe name and fails with "justfile does not contain
# recipe `<host>`"); the underlying scripts all take positional hosts.
_deploy_impl host="":
    python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ host }} {{ deploy_scope_arg }} {{ deploy_devices_only_arg }}

deploy-legacy:
    @just _deploy_impl

deploy host="":
    @just _deploy_impl {{ host }}

# ---------- Deploy (bootstrap-apks scope only — pure APK version bump, #166) ----------
# Skips termux_userland/post-ui/validate/control_node entirely; ~4x faster
# than a full deploy when the only thing that changed is an app's locked
# version (checksum/gh_tag/version_name in bootstrap_apks defaults).
# Usage: hosts=s24 just deploy-apks
deploy-apks:
    python3 control/bin/deploy_fleet.py {{ deploy_args }} --scope bootstrap-apks --devices-only

# ---------- Deploy (scripts scope only — on-device code push, #166) ----------
# Only the termux_userland tasks tagged `scripts`: ~/.stayturgid/bin, lib,
# boot and tasker syncs, retired-file cleanup, repair-script check. The
# boot-loop restart handler still fires when a synced script changed. Skips
# packages, SSH keys, CFEngine, otelcol, Shizuku, APKs and the Mac pass.
# Usage: hosts=s24 just deploy-scripts
deploy-scripts:
    python3 control/bin/deploy_fleet.py {{ deploy_args }} --scope scripts --devices-only

# ---------- Deploy Check (dry‑run) ----------
# Ansible --check only: no APK installs, no device writes. A green recap is
# NOT fleet convergence (#184). Apply with `just deploy`.
_deploy_check_impl host="":
    @echo "NOTE: just deploy-check is a DRY RUN (CHECK=1 / ansible --check). Nothing will be applied." >&2
    CHECK=1 python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ host }} {{ deploy_scope_arg }} {{ deploy_devices_only_arg }}

deploy-check-legacy:
    @just _deploy_check_impl

deploy-check host="":
    @just _deploy_check_impl {{ host }}

# ---------- Mac Workstation ----------
_deploy_mac_impl:
    {{ ansible_playbook }} {{ mac_site }} --tags mac

deploy-mac-legacy:
    @just _deploy_mac_impl

deploy-mac:
    @just _deploy_mac_impl

# ---------- Termux Layer ----------
_deploy_termux_impl host="":
    python3 control/bin/deploy_termux.py {{ deploy_args }} {{ host }}

deploy-termux-legacy:
    @just _deploy_termux_impl

# deploy_termux.py takes the inventory host as a positional argument and
# enforces single-host deploys itself (no --limit flag exists to forward).
deploy-termux host:
    @just _deploy_termux_impl {{ host }}

# ---------- Bootstrap SSH ----------
_bootstrap_ssh_impl host="":
    python3 control/bin/bootstrap_ssh.py {{ deploy_args }} {{ host }}

bootstrap-ssh-legacy:
    @just _bootstrap_ssh_impl

bootstrap-ssh host="":
    @just _bootstrap_ssh_impl {{ host }}

# ---------- Bootstrap APKs ----------
_bootstrap_apks_impl:
    {{ ansible_playbook }} ansible/playbooks/fleet/ensure-bootstrap-apks.yml {{ limit_flag }}

bootstrap-apks-legacy:
    @just _bootstrap_apks_impl

bootstrap-apks:
    @just _bootstrap_apks_impl

# ---------- Verify Bootstrap APKs ----------
_verify_bootstrap_apks_impl host="":
    {{ ansible_playbook }} ansible/playbooks/fleet/verify-bootstrap-apks.yml {{ if host == "" { limit_flag } else { "-l " + host } }}

verify-bootstrap-apks-legacy:
    @just _verify_bootstrap_apks_impl

verify-bootstrap-apks host="":
    @just _verify_bootstrap_apks_impl {{ host }}

# ---------- Ensure Shizuku ----------
_ensure_shizuku_impl:
    {{ ansible_playbook }} ansible/playbooks/fleet/ensure-shizuku.yml {{ limit_flag }}

ensure-shizuku-legacy:
    @just _ensure_shizuku_impl

ensure-shizuku:
    @just _ensure_shizuku_impl

# ---------- Secretspec Check ----------
secretspec-check:
    sudo-secretspec check --reason "just secretspec-check"

# Static gate: no second secret store, alternate manifest, plain CLI or retired artifact (#287)
secretspec-drift:
    python3 control/bin/check_secretspec_drift.py

# ---------- Health ----------
_health_impl:
    python3 control/bin/check_fleet_health.py

health-legacy:
    @just _health_impl

health:
    @just _health_impl

# ---------- Errors (last 24h) ----------
_errors_impl:
    python3 control/bin/check_fleet_health.py --hours 168

errors-legacy:
    @just _errors_impl

errors:
    @just _errors_impl

# ---------- Fix fireos-device Google ----------
_fix_hd8_google_impl:
    python3 control/bin/fix_hd8_google_stack.py fireos-device

fix-fireos-device-google-legacy:
    @just _fix_hd8_google_impl

fix-fireos-device-google:
    @just _fix_hd8_google_impl

# ---------- Ensure ET Mac ----------
_ensure_et_mac_impl:
    python3 control/bin/ensure_et_mac.py

ensure-et-mac-legacy:
    @just _ensure_et_mac_impl

ensure-et-mac:
    @just _ensure_et_mac_impl

# ---------- Check ET Mac ----------
_check_et_mac_impl:
    python3 control/bin/check_et_mac.py

check-et-mac-legacy:
    @just _check_et_mac_impl

check-et-mac:
    @just _check_et_mac_impl

# ---------- Collections ----------
_collections_impl:
    ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections

collections-legacy:
    @just _collections_impl

collections:
    @just _collections_impl

# ---------- Syntax Check ----------
_syntax_impl:
    {{ ansible_playbook }} ansible/playbooks/site.yml --syntax-check
    {{ ansible_playbook }} {{ mac_site }} --syntax-check
    {{ ansible_playbook }} ansible/playbooks/fleet/termux-pkg-upgrade.yml --syntax-check

syntax-legacy:
    @just _syntax_impl

syntax:
    @just _syntax_impl

# ---------- Termux PKG Upgrade ----------
_termux_pkg_upgrade_impl host="":
    python3 control/bin/termux_pkg_nightly.py {{ if host == "" { if hosts == "" { "" } else { "--limit " + replace(hosts, " ", ",") } } else { "--limit " + host } }}

termux-pkg-upgrade-legacy:
    @just _termux_pkg_upgrade_impl

termux-pkg-upgrade host="":
    @just _termux_pkg_upgrade_impl {{ host }}

# ---------- Verify Device ----------
_verify_device_impl:
    bash tests/run.sh device {{ hosts }}

verify device="":
    @just _verify_device_impl

# ---------- Verify Heal ----------
_verify_heal_impl:
    bash tests/run.sh device --heal {{ hosts }}

verify-heal host="":
    @just _verify_heal_impl

# ---------- Dryrun Alias ----------
dryrun: deploy-check-legacy

# ---------- Dryrun Termux ----------
_dryrun_termux_impl:
    {{ ansible_playbook }} ansible/playbooks/fleet/termux-userland.yml --check --diff {{ limit_flag }}

dryrun-termux-legacy:
    @just _dryrun_termux_impl

dryrun-termux:
    @just _dryrun_termux_impl

# ---------- SSH CA ----------
_ca_init_impl:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var("HOME") }}/.ssh/stayturgid_ca"
    if [ -f "$CA_KEY" ]; then
      echo "CA key already exists"
    else
      ssh-keygen -t ed25519 -f "$CA_KEY" -C "stayturgid-ca" -N ""
    fi
    ssh-keygen -lf "$CA_KEY"
    echo "@cert-authority * $(cat ${CA_KEY}.pub)" >> "{{ env_var("HOME") }}/.ssh/known_hosts" && echo "Added @cert-authority to ~/.ssh/known_hosts" || true

ca-init: _ca_init_impl

_ca_status_impl:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var("HOME") }}/.ssh/stayturgid_ca"
    echo "SSH CA:"
    if [ -f "$CA_KEY" ]; then ssh-keygen -lf "$CA_KEY"; else echo "  CA key missing (run just ca-init)"; fi
    if [ -f "${CA_KEY}.pub" ]; then echo "  pub: $(cat ${CA_KEY}.pub | awk '{print $3}')"; fi
    echo ""
    grep -c "cert-authority" ~/.ssh/known_hosts || true
    echo "  entries in Mac known_hosts"
    for host in stock-android-device fireos-device oneui-device; do
      ssh -o BatchMode=yes -o ConnectTimeout=5 $host 'grep -c cert-authority ~/.ssh/known_hosts' 2>/dev/null && echo "  $host known_hosts: ok" || echo "  $host: unreachable"
    done
    echo ""

ca-status: _ca_status_impl

# Sign all device host keys + deploy certs.
ca-sign:
    @mkdir -p "{{ env_var("HOME") }}/.ssh/host-certs"
    @{{ ansible_playbook }} ansible/playbooks/fleet/termux-userland.yml --tags ca 2>&1 || true
    @echo "Host certs signed. Run 'just deploy-mac' to update Mac known_hosts."

# ---------- FIRERPA ----------
_firerpa_deploy_impl:
    {{ ansible_playbook }} ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=true

firerpa-deploy-legacy:
    @hosts="{{ hosts }}" just _firerpa_deploy_impl

firerpa-deploy:
    @hosts="{{ hosts }}" just _firerpa_deploy_impl

_firerpa_remove_impl:
    {{ ansible_playbook }} ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=false

firerpa-remove-legacy:
    @hosts="{{ hosts }}" just _firerpa_remove_impl

firerpa-remove:
    @hosts="{{ hosts }}" just _firerpa_remove_impl

_firerpa_heal_impl:
    #!/usr/bin/env bash
    source ~/.venv-stayturgid-firerpa/bin/activate
    python3 control/bin/firerpa_heal.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}

firerpa-heal-legacy:
    @hosts="{{ hosts }}" just _firerpa_heal_impl

firerpa-heal host="":
    @hosts="{{ host }}" just _firerpa_heal_impl

_firerpa_health_impl:
    #!/usr/bin/env bash
    source ~/.venv-stayturgid-firerpa/bin/activate
    python3 control/bin/firerpa_health_monitor.py

firerpa-health-legacy:
    @just _firerpa_health_impl

firerpa-health:
    @just _firerpa_health_impl

# ---------- Verify Drift ----------
_verify_drift_impl host="":
    python3 control/bin/verify_drift.py {{ if host == "" { if hosts == "" { "--all" } else { "--host " + hosts } } else { "--host " + host } }}

verify-drift-legacy:
    @just _verify_drift_impl

verify-drift host="":
    @just _verify_drift_impl {{ host }}

# Play the battery locate sound on a device to find it by ear (ignores DND/quiet hours).
# Example: just ring s24
#          just ring hd8 120
ring host secs="60":
    python3 "{{ repo }}/control/bin/ring_device.py" "{{ host }}" "{{ secs }}"

# Battery watch (also runs inside every fleet-health pass): --dry-run prints, --test pings.
# Example: just battery-watch --dry-run
battery-watch *args:
    python3 "{{ repo }}/control/lib/battery_watch.py" {{ args }}
