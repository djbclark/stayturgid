# Fleet operations — deploy, verify, bootstrap, health, FIRERPA.

# Private implementations (prefixed with underscore) and legacy shims are provided for backward compatibility.
# Positional wrappers use `+host?` (optional positional host argument) and rely on environment variables for configuration.

# ---------- Deploy ----------
_deploy_impl:
    python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ deploy_scope_arg }}

deploy-legacy:
    @just _deploy_impl

deploy +host?:
    @just _deploy_impl {{ if host == "" { "" } else { "--limit " + host } }}

# ---------- Deploy Check (dry‑run) ----------
_deploy_check_impl:
    CHECK=1 python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ deploy_scope_arg }}

deploy-check-legacy:
    @just _deploy_check_impl

deploy-check +host?:
    @just _deploy_check_impl {{ if host == "" { "" } else { "--limit " + host } }}

# ---------- Mac Workstation ----------
_deploy_mac_impl:
    ansible-playbook {{ mac_site }} --tags mac

deploy-mac-legacy:
    @just _deploy_mac_impl

deploy-mac:
    @just _deploy_mac_impl

# ---------- Termux Layer ----------
_deploy_termux_impl:
    python3 control/bin/deploy_termux.py {{ deploy_args }}

deploy-termux-legacy:
    @just _deploy_termux_impl

deploy-termux +host?:
    @just _deploy_termux_impl {{ if host == "" { "" } else { "--limit " + host } }}

# ---------- Bootstrap SSH ----------
_bootstrap_ssh_impl:
    python3 control/bin/bootstrap_ssh.py {{ deploy_args }}

bootstrap-ssh-legacy:
    @just _bootstrap_ssh_impl

bootstrap-ssh +host?:
    @just _bootstrap_ssh_impl {{ if host == "" { "" } else { "--limit " + host } }}

# ---------- Bootstrap APKs ----------
_bootstrap_apks_impl:
    ansible-playbook ansible/playbooks/fleet/ensure-bootstrap-apks.yml {{ limit_flag }}

bootstrap-apks-legacy:
    @just _bootstrap_apks_impl

bootstrap-apks:
    @just _bootstrap_apks_impl

# ---------- Verify Bootstrap APKs ----------
_verify_bootstrap_apks_impl:
    ansible-playbook ansible/playbooks/fleet/verify-bootstrap-apks.yml {{ limit_flag }}

verify-bootstrap-apks-legacy:
    @just _verify_bootstrap_apks_impl

verify-bootstrap-apks +host?:
    @just _verify_bootstrap_apks_impl {{ if host == "" { "" } else { "-l " + host } }}

# ---------- Ensure Shizuku ----------
_ensure_shizuku_impl:
    ansible-playbook ansible/playbooks/fleet/ensure-shizuku.yml {{ limit_flag }}

ensure-shizuku-legacy:
    @just _ensure_shizuku_impl

ensure-shizuku:
    @just _ensure_shizuku_impl

# ---------- Secretspec Check ----------
_secretspec_check_impl:
    secretspec check --no-prompt --explain --provider dotenv --reason "just secretspec-check"

secretspec-check-legacy:
    @just _secretspec_check_impl

secretspec-check:
    @just _secretspec_check_impl

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

# ---------- Fix hd8 Google ----------
_fix_hd8_google_impl:
    python3 control/bin/fix_hd8_google_stack.py hd8

fix-hd8-google-legacy:
    @just _fix_hd8_google_impl

fix-hd8-google:
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

# ---------- Verify Play Autoupdate ----------
_verify_play_autoupdate_impl:
    STAYTURGID_VLM=1 python3 control/bin/verify_play_autoupdate.py {{ if hosts == "" { "hd8" } else { hosts } }}

verify-play-autoupdate-legacy:
    @just _verify_play_autoupdate_impl

verify-play-autoupdate +host?:
    @just _verify_play_autoupdate_impl {{ if host == "" { "hd8" } else { host } }}

# ---------- Verify hd8 Google ----------
_verify_hd8_google_impl:
    STAYTURGID_VLM=1 python3 control/bin/verify_hd8_google.py {{ if hosts == "" { "hd8" } else { hosts } }}

verify-hd8-google-legacy:
    @just _verify_hd8_google_impl

verify-hd8-google +host?:
    @just _verify_hd8_google_impl {{ if host == "" { "hd8" } else { host } }}

# ---------- Collections ----------
_collections_impl:
    ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections

collections-legacy:
    @just _collections_impl

collections:
    @just _collections_impl

# ---------- Syntax Check ----------
_syntax_impl:
    ansible-playbook ansible/playbooks/site.yml --syntax-check
    ansible-playbook {{ mac_site }} --syntax-check
    ansible-playbook ansible/playbooks/fleet/termux-pkg-upgrade.yml --syntax-check

syntax-legacy:
    @just _syntax_impl

syntax:
    @just _syntax_impl

# ---------- Termux PKG Upgrade ----------
_termux_pkg_upgrade_impl:
    python3 control/bin/termux_pkg_nightly.py {{ if hosts == "" { "" } else { "--limit " + replace(hosts, " ", ",") } }}

termux-pkg-upgrade-legacy:
    @just _termux_pkg_upgrade_impl

termux-pkg-upgrade +host?:
    @just _termux_pkg_upgrade_impl {{ if host == "" { "" } else { "--limit " + host } }}

# ---------- Verify Device ----------
_verify_device_impl:
    bash tests/run.sh device {{ hosts }}

verify +device?:
    @just _verify_device_impl

# ---------- Verify Heal ----------
_verify_heal_impl:
    bash tests/run.sh device --heal {{ hosts }}

verify-heal +host?:
    @just _verify_heal_impl

# ---------- Dryrun Alias ----------
dryrun: deploy-check-legacy

# ---------- Dryrun Termux ----------
_dryrun_termux_impl:
    ansible-playbook ansible/playbooks/fleet/termux-userland.yml --check --diff {{ limit_flag }}

dryrun-termux-legacy:
    @just _dryrun_termux_impl

dryrun-termux:
    @just _dryrun_termux_impl

# ---------- SSH CA ----------
_ca_init_impl:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var(\"HOME\") }}/.ssh/stayturgid_ca"
    if [ -f "$CA_KEY" ]; then
      echo "CA key already exists"
    else
      ssh-keygen -t ed25519 -f "$CA_KEY" -C "stayturgid-ca" -N ""
    fi
    ssh-keygen -lf "$CA_KEY"
    echo "@cert-authority * $(cat ${CA_KEY}.pub)" >> "{{ env_var(\"HOME\") }}/.ssh/known_hosts" && echo "Added @cert-authority to ~/.ssh/known_hosts" || true

ca-init: _ca_init_impl

_ca_status_impl:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var(\"HOME\") }}/.ssh/stayturgid_ca"
    echo "SSH CA:"
    if [ -f "$CA_KEY" ]; then ssh-keygen -lf "$CA_KEY"; else echo "  CA key missing (run just ca-init)"; fi
    if [ -f "${CA_KEY}.pub" ]; then echo "  pub: $(cat ${CA_KEY}.pub | awk '{print $3}')"; fi
    echo ""
    grep -c "cert-authority" ~/.ssh/known_hosts || true
    echo "  entries in Mac known_hosts"
    for host in p7a hd8 s24; do
      ssh -o BatchMode=yes -o ConnectTimeout=5 $host 'grep -c cert-authority ~/.ssh/known_hosts' 2>/dev/null && echo "  $host known_hosts: ok" || echo "  $host: unreachable"
    done
    echo ""

ca-status: _ca_status_impl

# ---------- FIRERPA ----------
_firerpa_deploy_impl:
    ansible-playbook ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=true

firerpa-deploy-legacy:
    @just _firerpa_deploy_impl

firerpa-deploy:
    @just _firerpa_deploy_impl

_firerpa_remove_impl:
    ansible-playbook ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=false

firerpa-remove-legacy:
    @just _firerpa_remove_impl

firerpa-remove:
    @just _firerpa_remove_impl

_firerpa_heal_impl:
    #!/usr/bin/env bash
    source /tmp/lamda-venv/bin/activate
    python3 control/bin/firerpa_heal.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}

firerpa-heal-legacy:
    @just _firerpa_heal_impl

firerpa-heal +host?:
    @just _firerpa_heal_impl {{ if host == "" { "--all" } else { "--host " + host } }}

_firerpa_health_impl:
    #!/usr/bin/env bash
    source /tmp/lamda-venv/bin/activate
    python3 control/bin/firerpa_health_monitor.py

firerpa-health-legacy:
    @just _firerpa_health_impl

firerpa-health:
    @just _firerpa_health_impl

# ---------- Verify Drift ----------
_verify_drift_impl:
    python3 control/bin/verify_drift.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}

verify-drift-legacy:
    @just _verify_drift_impl

verify-drift +host?:
    @just _verify_drift_impl {{ if host == "" { "--all" } else { "--host " + host } }}

# Full fleet deploy (ansible/playbooks/site.yml).
deploy:
    python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ deploy_scope_arg }}

# Dry-run deploy (--check --diff).
deploy-check:
    CHECK=1 python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ deploy_scope_arg }}

# Mac workstation only (brew, launchd, conf).
deploy-mac:
    ansible-playbook {{ mac_site }} --tags mac

# Termux layer only (termux_userland role).
deploy-termux:
    python3 control/bin/deploy_termux.py {{ deploy_args }}

# ADB bootstrap Termux SSH keys + sshd.
bootstrap-ssh:
    python3 control/bin/bootstrap_ssh.py {{ deploy_args }}

# ADB install prerequisite APKs (no device interaction).
bootstrap-apks:
    ansible-playbook ansible/playbooks/fleet/ensure-bootstrap-apks.yml {{ limit_flag }}

# Check APK versions before deploy.
verify-bootstrap-apks:
    ansible-playbook ansible/playbooks/fleet/verify-bootstrap-apks.yml {{ limit_flag }}

# Start Shizuku + apply fleet profile over ADB.
ensure-shizuku:
    ansible-playbook ansible/playbooks/fleet/ensure-shizuku.yml {{ limit_flag }}

# Verify all required secrets are set.
secretspec-check:
    secretspec check --no-prompt --explain --provider dotenv --reason "just secretspec-check"

# Mac fleet-health summary (exit 1 = tell operator).
health:
    python3 control/bin/check_fleet_health.py

# Show recent device errors from all logs (last 24h).
errors:
    python3 control/bin/check_fleet_health.py --hours 168

# Pin sideloaded GMS/Play on Fire hd8 (see docs).
fix-hd8-google:
    python3 control/bin/fix_hd8_google_stack.py hd8

# Phone→Mac ET: fleet keys in authorized_keys.
ensure-et-mac:
    python3 control/bin/ensure_et_mac.py

# Soft-check etserver + fleet key block.
check-et-mac:
    python3 control/bin/check_et_mac.py

# Play Store auto-update VLM check (STAYTURGID_VLM=1).
verify-play-autoupdate:
    STAYTURGID_VLM=1 python3 control/bin/verify_play_autoupdate.py {{ if hosts == "" { "hd8" } else { hosts } }}

# Stack + crash + auto-update close-out (hd8).
verify-hd8-google:
    STAYTURGID_VLM=1 python3 control/bin/verify_hd8_google.py {{ if hosts == "" { "hd8" } else { hosts } }}

# Install ansible-galaxy collections.
collections:
    ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections

# Syntax-check site.yml + control_node/site.yml.
syntax:
    ansible-playbook ansible/playbooks/site.yml --syntax-check
    ansible-playbook {{ mac_site }} --syntax-check
    ansible-playbook ansible/playbooks/fleet/termux-pkg-upgrade.yml --syntax-check

# Nightly-style Termux pkg update/upgrade (all hosts).
termux-pkg-upgrade hosts="":
    @just _termux-pkg-upgrade {{ hosts }}

# Read-only device tier (TAP).
verify +device:
    bash tests/run.sh device {{ hosts }}

# Device tier with self-heal steps.
verify-heal:
    bash tests/run.sh device --heal {{ hosts }}

# Alias for deploy-check.
dryrun: deploy-check

# Ansible --check on termux-userland.yml only.
dryrun-termux:
    ansible-playbook ansible/playbooks/fleet/termux-userland.yml --check --diff {{ limit_flag }}

# ── SSH Certificate Authority ──────────────────────────────────────────────

# Generate CA key pair (~/.ssh/stayturgid_ca).
ca-init: _ca-init

# Sign all device host keys + deploy certs.
ca-sign:
    @mkdir -p "{{ env_var("HOME") }}/.ssh/host-certs"
    @ansible-playbook ansible/playbooks/fleet/termux-userland.yml --tags ca 2>&1 || true
    @echo "Host certs signed. Run 'just deploy-mac' to update Mac known_hosts."

# Show CA key fingerprint + cert status.
ca-status: _ca-status

[private]
_ca-init:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var("HOME") }}/.ssh/stayturgid_ca"
    if [ -f "$CA_KEY" ]; then
      echo "CA key already exists"
    else
      ssh-keygen -t ed25519 -f "$CA_KEY" -C "stayturgid-ca" -N ""
    fi
    ssh-keygen -lf "$CA_KEY"
    echo "@cert-authority * $(cat ${CA_KEY}.pub)" >> "{{ env_var("HOME") }}/.ssh/known_hosts" \
      && echo "Added @cert-authority to ~/.ssh/known_hosts" || true

[private]
_ca-status:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var("HOME") }}/.ssh/stayturgid_ca"
    echo "SSH CA:"
    if [ -f "$CA_KEY" ]; then ssh-keygen -lf "$CA_KEY"; else echo "  CA key missing (run just ca-init)"; fi
    if [ -f "${CA_KEY}.pub" ]; then echo "  pub: $(cat ${CA_KEY}.pub | awk '{print $3}')"; fi
    echo ""
    grep -c "cert-authority" ~/.ssh/known_hosts || true
    echo "  entries in Mac known_hosts"
    for host in p7a hd8 s24; do
      ssh -o BatchMode=yes -o ConnectTimeout=5 $host 'grep -c cert-authority ~/.ssh/known_hosts' 2>/dev/null \
        && echo "  $host known_hosts: ok" || echo "  $host: unreachable"
    done
    echo ""

# ── FIRERPA/lamda failsafe daemon ─────────────────────────────────────────

# Install + configure + start FIRERPA.
firerpa-deploy:
    ansible-playbook ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=true

# Stop + uninstall FIRERPA.
firerpa-remove:
    ansible-playbook ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=false

# Repair stayturgid via FIRERPA gRPC API.
firerpa-heal:
    #!/usr/bin/env bash
    source /tmp/lamda-venv/bin/activate
    python3 control/bin/firerpa_heal.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}

# Check FIRERPA fleet health now.
firerpa-health:
    #!/usr/bin/env bash
    source /tmp/lamda-venv/bin/activate
    python3 control/bin/firerpa_health_monitor.py

# Ansible-based verification + drift report.
verify-drift:
    python3 control/bin/verify_drift.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}
