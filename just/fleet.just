# Fleet operations — deploy, verify, bootstrap, health, FIRERPA.

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
