# Services — Hermes, dashboard, landing, OpenCode, VLM.

# ── VLM (optional Mac UI-TARS gates — see docs/vlm.md) ────────────────────

# Ansible: brew llama.cpp + download weights (~6GB).
vlm-install:
    ansible-playbook {{ mac_site }} -e stayturgid_vlm_enabled=true --tags vlm-models

# Manual foreground start (no launchd).
vlm-server:
    bash control/vlm/ui-tars/ui_tars_server.sh

# Smoke-test server + client.
vlm-check:
    python3 control/bin/vlm_check.py

# Ansible: launchd agent.
vlm-service-install:
    ansible-playbook {{ mac_site }} -e stayturgid_vlm_enabled=true --tags vlm-service

# Health + launchctl summary.
vlm-service-status:
    bash control/vlm/ui-tars/vlm_service.sh status

# launchctl bootout + stop manual.
vlm-service-stop:
    bash control/vlm/ui-tars/vlm_service.sh stop

# kickstart launchd agent.
vlm-service-restart:
    bash control/vlm/ui-tars/vlm_service.sh restart

# Stop/start launchd QA cycle.
vlm-smoke:
    bash control/vlm/ui-tars/vlm_smoke.sh

# Alias for vlm-service-stop.
vlm-stop: vlm-service-stop

# Diff RevengeQuickSwitcher/VLM.md best practices.
vlm-upstream-check:
    python3 control/bin/vlm_upstream_check.py --notify

# ── Hermes Agent (Telegram gateway + OpenCode API) ─────────────────────────

# Start the launchd gateway service.
hermes-start:
    hermes gateway start

# Stop the gateway service.
hermes-stop:
    hermes gateway stop

# Restart the gateway service.
hermes-restart:
    hermes gateway restart

# Quick gateway status (PID, platform state).
hermes-status:
    @hermes gateway status
    @echo ""
    @python3 -c "import json,sys; s=json.load(open('{{ env_var('HOME') }}/.hermes/gateway_state.json')); tg=s.get('platforms',{}).get('telegram',{}); print(f'Telegram: {tg.get(\"state\",\"unknown\")}')"

# Full status (model, auth, providers, sessions).
hermes-status-full:
    hermes status

# View recent gateway log (HERMES_LINES=N).
hermes-logs lines="100":
    hermes logs gateway -n {{ lines }}

# Follow gateway log in real time.
hermes-logs-follow:
    hermes logs gateway -f

# Diagnose config + dependencies.
hermes-doctor:
    hermes doctor

# Ansible: install, configure, launchd plist.
hermes-deploy:
    ansible-playbook {{ mac_site }} --tags hermes

# Ansible: remove plist + unload launchd.
hermes-disable:
    ansible-playbook {{ mac_site }} --tags agents -e stayturgid_hermes_enabled=false

# Update hermes-agent package.
hermes-update:
    hermes update

# ── OpenCode web (fleet-reachable web UI on http://<ts-ip>:4096) ───────────

opencode_web_label := "com.stayturgid.opencode-web"
opencode_web_port := "4096"

# Health check + launchctl state.
opencode-web-status:
    @echo "OpenCode web:"
    @launchctl list {{ opencode_web_label }} 2>/dev/null || echo "  not loaded"
    @curl -sf -o /dev/null -w "  HTTP %{http_code}" http://127.0.0.1:{{ opencode_web_port }}/ 2>/dev/null || echo "  HTTP unreachable"
    @echo ""

# kickstart launchd agent.
opencode-web-restart:
    launchctl kickstart -k gui/$(id -u)/{{ opencode_web_label }}

# Ansible: install + load launchd agent.
opencode-web-deploy:
    ansible-playbook {{ mac_site }} --tags agents -e stayturgid_opencode_web_enabled=true
    @echo ""
    @-launchctl kickstart -k gui/$(id -u)/{{ opencode_web_label }} 2>/dev/null
    @echo "OpenCode web deployed. Verify: just opencode-web-status"

# Ansible: remove plist + unload.
opencode-web-disable:
    ansible-playbook {{ mac_site }} --tags agents -e stayturgid_opencode_web_enabled=false

# ── Fleet dashboard (Flask + HTMX, port 4097) ──────────────────────────────

dashboard_label := "com.stayturgid.dashboard"

# Health check + launchctl state.
dashboard-status:
    @echo "Fleet dashboard:"
    @launchctl list {{ dashboard_label }} 2>/dev/null || echo "  not loaded"
    @curl -sf -o /dev/null -w "  HTTP %{http_code}" http://127.0.0.1:4097/health 2>/dev/null || echo "  HTTP unreachable"
    @echo ""

# kickstart launchd agent.
dashboard-restart:
    launchctl kickstart -k gui/$(id -u)/{{ dashboard_label }}

# Ansible: install + load launchd agent.
dashboard-deploy:
    ansible-playbook {{ mac_site }} --tags agents -e stayturgid_dashboard_enabled=true
    @echo ""
    @-launchctl kickstart -k gui/$(id -u)/{{ dashboard_label }} 2>/dev/null
    @echo "Dashboard deployed. Verify: just dashboard-status"

# Ansible: remove plist + unload.
dashboard-disable:
    ansible-playbook {{ mac_site }} --tags agents -e stayturgid_dashboard_enabled=false

# tail -f dashboard.log.
dashboard-logs:
    tail -f "{{ env_var("HOME") }}/.config/stayturgid/logs/dashboard.log"

# ── Network landing page (service directory on http://localhost:8088) ──────

landing_label := "com.stayturgid.landing"

# Health check + launchctl state.
landing-status:
    @echo "Network landing:"
    @launchctl list {{ landing_label }} 2>/dev/null || echo "  not loaded"
    @curl -sf -o /dev/null -w "  HTTP %{http_code}" http://127.0.0.1:8088/health 2>/dev/null || echo "  HTTP unreachable"
    @echo ""

# kickstart launchd agent.
landing-restart:
    launchctl kickstart -k gui/$(id -u)/{{ landing_label }}

# Load launchd agent.
landing-deploy:
    launchctl load "{{ env_var("HOME") }}/Library/LaunchAgents/{{ landing_label }}.plist" 2>/dev/null || true
    @echo "Landing page deployed. Verify: just landing-status"

# Stop + unload launchd agent.
landing-disable:
    -launchctl unload "{{ env_var("HOME") }}/Library/LaunchAgents/{{ landing_label }}.plist" 2>/dev/null
    @echo "Landing page disabled."

# Run service discovery scan.
landing-discover:
    python3 control/landing/discover.py
