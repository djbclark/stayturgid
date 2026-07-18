# Fleet operations — deploy, verify, bootstrap, health, FIRERPA.

# Private implementations (prefixed with underscore)

_deploy_impl:
    python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ deploy_scope_arg }}

_deploy_check_impl:
    CHECK=1 python3 control/bin/deploy_fleet.py {{ deploy_args }} {{ deploy_scope_arg }}

_deploy_mac_impl:
    ansible-playbook {{ mac_site }} --tags mac

_deploy_termux_impl:
    python3 control/bin/deploy_termux.py {{ deploy_args }}

_bootstrap_ssh_impl:
    python3 control/bin/bootstrap_ssh.py {{ deploy_args }}

_bootstrap_apks_impl:
    ansible-playbook ansible/playbooks/fleet/ensure-bootstrap-apks.yml {{ limit_flag }}

_verify_bootstrap_apks_impl:
    ansible-playbook ansible/playbooks/fleet/verify-bootstrap-apks.yml {{ limit_flag }}

_ensure_shizuku_impl:
    ansible-playbook ansible/playbooks/fleet/ensure-shizuku.yml {{ limit_flag }}

_secretspec_check_impl:
    secretspec check --no-prompt --explain --provider dotenv --reason "just secretspec-check"

_health_impl:
    python3 control/bin/check_fleet_health.py

_errors_impl:
    python3 control/bin/check_fleet_health.py --hours 168

_fix_hd8_google_impl:
    python3 control/bin/fix_hd8_google_stack.py hd8

_ensure_et_mac_impl:
    python3 control/bin/ensure_et_mac.py

_check_et_mac_impl:
    python3 control/bin/check_et_mac.py

_verify_play_autoupdate_impl:
    STAYTURGID_VLM=1 python3 control/bin/verify_play_autoupdate.py {{ if hosts == "" { "hd8" } else { hosts } }}

_verify_hd8_google_impl:
    STAYTURGID_VLM=1 python3 control/bin/verify_hd8_google.py {{ if hosts == "" { "hd8" } else { hosts } }}

_collections_impl:
    ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections

_syntax_impl:
    ansible-playbook ansible/playbooks/site.yml --syntax-check
    ansible-playbook {{ mac_site }} --syntax-check
    ansible-playbook ansible/playbooks/fleet/termux-pkg-upgrade.yml --syntax-check

_termux_pkg_upgrade_impl:
    python3 control/bin/termux_pkg_nightly.py {{ if hosts == "" { "" } else { "--limit " + replace(hosts, " ", ",") } }}

_verify_device_impl:
    bash tests/run.sh device {{ hosts }}

_verify_heal_impl:
    bash tests/run.sh device --heal {{ hosts }}

_dryrun_impl:
    @just deploy-check

_dryrun_termux_impl:
    ansible-playbook ansible/playbooks/fleet/termux-userland.yml --check --diff {{ limit_flag }}

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

_ca_status_impl:
    #!/usr/bin/env bash
    CA_KEY="{{ env_var("HOME") }}/.ssh/stayturgid_ca"
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

_firerpa_deploy_impl:
    ansible-playbook ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=true

_firerpa_remove_impl:
    ansible-playbook ansible/playbooks/fleet/firerpa.yml {{ limit_flag }} -e firerpa_enabled=false

_firerpa_heal_impl:
    #!/usr/bin/env bash
    source /tmp/lamda-venv/bin/activate
    python3 control/bin/firerpa_heal.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}

_firerpa_health_impl:
    #!/usr/bin/env bash
    source /tmp/lamda-venv/bin/activate
    python3 control/bin/firerpa_health_monitor.py

_verify_drift_impl:
    python3 control/bin/verify_drift.py {{ if hosts == "" { "--all" } else { "--host " + hosts } }}

# Legacy shims (visible in just --list)

deploy-legacy:
    @just _deploy_impl

deploy-check-legacy:
    @just _deploy_check_impl

deploy-mac-legacy:
    @just _deploy_mac_impl

deploy-termux-legacy:
    @just _deploy_termux_impl

bootstrap-ssh-legacy:
    @just _bootstrap_ssh_impl

bootstrap-apks-legacy:
    @just _bootstrap_apks_impl

verify-bootstrap-apks-legacy:
    @just _verify_bootstrap_apks_impl

ensure-shizuku-legacy:
    @just _ensure_shizuku_impl

secretspec-check-legacy:
    @just _secretspec_check_impl

health-legacy:
    @just _health_impl

errors-legacy:
    @just _errors_impl

fix-hd8-google-legacy:
    @just _fix_hd8_google_impl

ensure-et-mac-legacy:
    @just _ensure_et_mac_impl

check-et-mac-legacy:
    @just _check_et_mac_impl

verify-play-autoupdate-legacy:
    @just _verify_play_autoupdate_impl

verify-hd8-google-legacy:
    @just _verify_hd8_google_impl

collections-legacy:
    @just _collections_impl

syntax-legacy:
    @just _syntax_impl

termux-pkg-upgrade-legacy:
    @just _termux_pkg_upgrade_impl

verify-device-legacy:
    @just _verify_device_impl

verify-heal-legacy:
    @just _verify_heal_impl

dryrun-legacy:
    @just _dryrun_impl

dryrun-termux-legacy:
    @just _dryrun_termux_impl

ca-init-legacy:
    @just _ca_init_impl

ca-status-legacy:
    @just _ca_status_impl

firerpa-deploy-legacy:
    @just _firerpa_deploy_impl

firerpa-remove-legacy:
    @just _firerpa_remove_impl

firerpa-heal-legacy:
    @just _firerpa_heal_impl

firerpa-health-legacy:
    @just _firerpa_health_impl

verify-drift-legacy:
    @just _verify_drift_impl

# Positional wrappers (new public API)

deploy hosts="":
    @just --set hosts {{hosts}} deploy-legacy

deploy-check hosts="":
    @just --set hosts {{hosts}} deploy-check-legacy

deploy-mac:
    @just deploy-mac-legacy

deploy-termux hosts="":
    @just --set hosts {{hosts}} deploy-termux-legacy

bootstrap-ssh hosts="":
    @just --set hosts {{hosts}} bootstrap-ssh-legacy

bootstrap-apks hosts="":
    @just --set hosts {{hosts}} bootstrap-apks-legacy

verify-bootstrap-apks hosts="":
    @just --set hosts {{hosts}} verify-bootstrap-apks-legacy

ensure-shizuku hosts="":
    @just --set hosts {{hosts}} ensure-shizuku-legacy

secretspec-check:
    @just secretspec-check-legacy

health:
    @just health-legacy

errors:
    @just errors-legacy

fix-hd8-google:
    @just fix-hd8-google-legacy

ensure-et-mac:
    @just ensure-et-mac-legacy

check-et-mac:
    @just check-et-mac-legacy

verify-play-autoupdate hosts="":
    @just --set hosts {{hosts}} verify-play-autoupdate-legacy

verify-hd8-google hosts="":
    @just --set hosts {{hosts}} verify-hd8-google-legacy

collections:
    @just collections-legacy

syntax:
    @just syntax-legacy

termux-pkg-upgrade hosts="":
    @just --set hosts {{hosts}} termux-pkg-upgrade-legacy

verify device hosts="":
    @just --set hosts {{hosts}} verify-device-legacy

verify-heal hosts="":
    @just --set hosts {{hosts}} verify-heal-legacy

dryrun hosts="":
    @just --set hosts {{hosts}} dryrun-legacy

dryrun-termux hosts="":
    @just --set hosts {{hosts}} dryrun-termux-legacy

ca-init:
    @just ca-init-legacy

ca-status:
    @just ca-status-legacy

firerpa-deploy hosts="":
    @just --set hosts {{hosts}} firerpa-deploy-legacy

firerpa-remove hosts="":
    @just --set hosts {{hosts}} firerpa-remove-legacy

firerpa-heal hosts="":
    @just --set hosts {{hosts}} firerpa-heal-legacy

firerpa-health:
    @just firerpa-health-legacy

verify-drift hosts="":
    @just --set hosts {{hosts}} verify-drift-legacy
