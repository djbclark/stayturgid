# stayturgid — common commands (run `make help`).
#
# Variables (optional on most targets):
#   HOSTS=s24       Limit to one or more inventory hosts (comma-free: HOSTS="s24 hd8")
#   SCOPE=full      deploy scope: full | fdroid | play | app-stores

SHELL := /bin/bash
.DEFAULT_GOAL := help

REPO := $(CURDIR)
export ANSIBLE_CONFIG := $(REPO)/ansible/ansible.cfg

VENV := .venv-test
COLLECTIONS := android_common termux obtainium fdroid play
PYTEST := $(shell [ -x $(VENV)/bin/pytest ] && echo $(VENV)/bin/pytest || command -v pytest)
ANSIBLE_TEST := $(shell [ -x $(VENV)/bin/ansible-test ] && echo $(abspath $(VENV))/bin/ansible-test || command -v ansible-test)

HOSTS ?=
SCOPE ?= full
# Space-separated host list → deploy_fleet.py positional args
DEPLOY_ARGS := $(if $(HOSTS),$(HOSTS),)
DEPLOY_SCOPE_ARG := $(if $(filter-out full,$(SCOPE)),--scope $(SCOPE),)

MAC_SITE := ansible/playbooks/control_node/site.yml
VLM_ANSIBLE := ansible-playbook $(MAC_SITE) -e stayturgid_vlm_enabled=true

.PHONY: help all configure check unit test unit-and-pytest pytest ansible-test test-venv \
        lint clean verify verify-heal device dryrun dryrun-termux \
        health fix-hd8-google deploy deploy-check collections bootstrap-ssh deploy-termux deploy-mac syntax \
        termux-pkg-upgrade vlm-upstream-check \
        vlm-install vlm-server vlm-check vlm-stop vlm-service-install vlm-service-status \
        vlm-service-stop vlm-service-restart vlm-smoke verify-play-autoupdate verify-hd8-google \
        ensure-et-mac check-et-mac \
        hermes-start hermes-stop hermes-restart hermes-status hermes-status-full \
        hermes-logs hermes-logs-follow hermes-doctor hermes-deploy hermes-disable hermes-update \
        opencode-web-status opencode-web-restart \
        opencode-web-deploy opencode-web-disable \
        ca-init ca-sign ca-status \
        firerpa-deploy firerpa-remove firerpa-heal

# ------------------------------------------------------------------------------
# Help
# ------------------------------------------------------------------------------

help:
	@echo ""
	@echo "stayturgid — common make targets"
	@echo ""
	@echo "Variables:  HOSTS=<alias>   limit to inventory host(s), e.g. HOSTS=s24"
	@echo "            SCOPE=<name>    deploy scope: full (default) | fdroid | play | app-stores"
	@echo ""
	@echo "Fleet (live phones):"
	@echo "  make deploy [HOSTS=s24]           Full fleet deploy (ansible/playbooks/site.yml)"
	@echo "  make deploy-check [HOSTS=s24]     Ansible dry run (--check --diff)"
	@echo "  make deploy-mac                   Mac workstation only (brew, launchd, conf)"
	@echo "  make deploy-termux [HOSTS=s24]    Termux layer only (termux_userland role)"
	@echo "  make bootstrap-ssh [HOSTS=s24]    ADB bootstrap Termux SSH keys + sshd"
	@echo "  make health                     Mac fleet-health summary (exit 1 = tell operator)"
	@echo "  make fix-hd8-google             Pin sideloaded GMS/Play on Fire hd8 (see docs)"
	@echo "  make ensure-et-mac              Phone→Mac ET: fleet keys in authorized_keys"
	@echo "  make check-et-mac               Soft-check etserver + fleet key block"
	@echo "  make verify-play-autoupdate     Play Store auto-update VLM check (STAYTURGID_VLM=1)"
	@echo "  make verify-hd8-google          Stack + crash + auto-update close-out (hd8)"
	@echo "  make collections                Install ansible-galaxy collections"
	@echo "  make syntax                     Syntax-check site.yml + control_node/site.yml"
	@echo "  make termux-pkg-upgrade [HOSTS=]  Nightly-style Termux pkg update/upgrade (all hosts)"
	@echo ""
	@echo "Verify (SSH to devices):"
	@echo "  make verify [HOSTS=s24]           Read-only device tier (TAP)"
	@echo "  make verify-heal [HOSTS=s24]      Device tier with self-heal steps"
	@echo "  make dryrun [HOSTS=s24]           Alias for deploy-check"
	@echo "  make dryrun-termux [HOSTS=s24]    Ansible --check on termux-userland.yml only"
	@echo ""
	@echo "Test & lint (no device required):"
	@echo "  make test                         Unit + pytest + ansible-test (CI default)"
	@echo "  make check                        Code-only syntax / import checks"
	@echo "  make unit                         Device-free unit tests (shell TAP)"
	@echo "  make pytest                       Python unit tests (Termux script twins)"
	@echo "  make ansible-test                 ansible-test units for collections"
	@echo "  make test-venv                    Create .venv-test (once)"
	@echo "  make lint                         shellcheck + ansible-lint + yamllint"
	@echo "  make configure                    Report tool availability → .config.mk"
	@echo "  make clean                        Remove temporary build + test artifacts"
	@echo ""
	@echo "VLM (optional Mac UI-TARS gates — vendor-neutral; see docs/vlm.md):"
	@echo "  make vlm-install                  Ansible: brew llama.cpp + download weights (~6GB)"
	@echo "  make vlm-service-install          Ansible: launchd agent (persists across login)"
	@echo "  make vlm-service-status           health + launchctl summary"
	@echo "  make vlm-check                    Smoke-test server + client"
	@echo "  make vlm-smoke                    Stop/start launchd QA cycle"
	@echo "  make vlm-server                   Manual foreground start (no launchd)"
	@echo "  make vlm-service-stop             launchctl bootout + stop manual"
	@echo "  make vlm-service-restart          kickstart launchd agent"
	@echo "  make vlm-stop                     Alias for vlm-service-stop"
	@echo "  make vlm-upstream-check           Diff RevengeQuickSwitcher/VLM.md best practices"
	@echo ""
	@echo "Hermes (Telegram gateway + OpenCode agent):"
	@echo "  make hermes-start                 Start the launchd gateway service"
	@echo "  make hermes-stop                  Stop the gateway service"
	@echo "  make hermes-restart               Restart the gateway service"
	@echo "  make hermes-status                Quick gateway status (PID, platform state)"
	@echo "  make hermes-status-full           Full status (model, auth, providers, sessions)"
	@echo "  make hermes-logs                  View recent gateway log (HERMES_LINES=N)"
	@echo "  make hermes-logs-follow           Follow gateway log in real time"
	@echo "  make hermes-doctor                Diagnose config + dependencies"
	@echo "  make hermes-deploy                Ansible: install, configure, launchd plist"
	@echo "  make hermes-disable               Ansible: remove plist + unload launchd"
	@echo "  make hermes-update                Update hermes-agent package"
	@echo ""
	@echo "OpenCode web (fleet-reachable web UI on http://<ts-ip>:4096):"
	@echo "  make opencode-web-deploy           Ansible: install + load launchd agent"
	@echo "  make opencode-web-status           Health check + launchctl state"
	@echo "  make opencode-web-restart          kickstart launchd agent"
	@echo "  make opencode-web-disable          Ansible: remove plist + unload"
	@echo ""
	@echo "SSH CA (certificate authority for fleet host-key trust):"
	@echo "  make ca-status                     Show CA key fingerprint + cert status"
	@echo "  make ca-init                       Generate CA key pair (~/.ssh/stayturgid_ca)"
	@echo "  make ca-sign                       Sign all device host keys + deploy certs"
	@echo ""
	@echo "FIRERPA (optional on-device failsafe daemon):"
	@echo "  make firerpa-deploy [HOSTS=s24]     Install + configure + start FIRERPA"
	@echo "  make firerpa-remove [HOSTS=s24]     Stop + uninstall FIRERPA"
	@echo "  make firerpa-heal [HOSTS=s24]       Repair stayturgid via FIRERPA gRPC API"
	@echo ""
	@echo "Examples:"
	@echo "  make deploy HOSTS=s24"
	@echo "  CHECK=1 make deploy HOSTS=hd8    # same as make deploy-check HOSTS=hd8"
	@echo "  make verify HOSTS=\"s24 p7a\""
	@echo ""

# ------------------------------------------------------------------------------
# Fleet operations
# ------------------------------------------------------------------------------

deploy:
	python3 control/bin/deploy_fleet.py $(DEPLOY_ARGS) $(DEPLOY_SCOPE_ARG)

deploy-check:
	CHECK=1 python3 control/bin/deploy_fleet.py $(DEPLOY_ARGS) $(DEPLOY_SCOPE_ARG)

deploy-mac:
	ansible-playbook $(MAC_SITE) --tags mac

deploy-termux:
	python3 control/bin/deploy_termux.py $(DEPLOY_ARGS)

bootstrap-ssh:
	python3 control/bin/bootstrap_ssh.py $(DEPLOY_ARGS)

health:
	python3 control/bin/check_fleet_health.py

# Phone→Mac Eternal Terminal (fleet keys + etserver soft check)
ensure-et-mac:
	python3 control/bin/ensure_et_mac.py

check-et-mac:
	python3 control/bin/check_et_mac.py

fix-hd8-google:
	python3 control/bin/fix_hd8_google_stack.py hd8

verify-play-autoupdate:
	STAYTURGID_VLM=1 python3 control/bin/verify_play_autoupdate.py $(or $(HOSTS),hd8)

verify-hd8-google:
	STAYTURGID_VLM=1 python3 control/bin/verify_hd8_google.py $(or $(HOSTS),hd8)

vlm-install:
	$(VLM_ANSIBLE) --tags vlm-models

vlm-server:
	bash control/vlm/ui-tars/ui_tars_server.sh

vlm-check:
	python3 control/bin/vlm_check.py

vlm-service-install:
	$(VLM_ANSIBLE) --tags vlm-service

vlm-service-status:
	bash control/vlm/ui-tars/vlm_service.sh status

vlm-service-stop:
	bash control/vlm/ui-tars/vlm_service.sh stop

vlm-service-restart:
	bash control/vlm/ui-tars/vlm_service.sh restart

vlm-smoke:
	bash control/vlm/ui-tars/vlm_smoke.sh

vlm-stop: vlm-service-stop

# Sibling-project VLM best practices (~/src/RevengeQuickSwitcher/VLM.md).
# Weekly launchd: com.stayturgid.vlm-upstream-check (make deploy-mac).
vlm-upstream-check:
	python3 control/bin/vlm_upstream_check.py --notify

# ------------------------------------------------------------------------------
# Hermes Agent (Telegram gateway + OpenCode API)
# ------------------------------------------------------------------------------

HERMES_LINES ?= 100

hermes-start:
	hermes gateway start

hermes-stop:
	hermes gateway stop

hermes-restart:
	hermes gateway restart

hermes-status:
	@hermes gateway status
	@echo ""
	@python3 -c "import json,sys; s=json.load(open('$(HOME)/.hermes/gateway_state.json')); tg=s.get('platforms',{}).get('telegram',{}); print(f'Telegram: {tg.get(\"state\",\"unknown\")}')"

hermes-status-full:
	hermes status

hermes-logs:
	hermes logs gateway -n $(HERMES_LINES)

hermes-logs-follow:
	hermes logs gateway -f

hermes-doctor:
	hermes doctor

hermes-deploy:
	ansible-playbook $(MAC_SITE) --tags hermes

hermes-disable:
	ansible-playbook $(MAC_SITE) --tags agents -e stayturgid_hermes_enabled=false

hermes-update:
	hermes update

# ── OpenCode web (control-node launchd) ────────────────────────────────────
OPENCODE_LABEL := com.stayturgid.opencode-web
OPENCODE_PORT := 4096

opencode-web-status:
	@echo "OpenCode web:"
	@launchctl list $(OPENCODE_LABEL) 2>/dev/null || echo "  not loaded"
	@curl -sf -o /dev/null -w "  HTTP %{http_code}" http://127.0.0.1:$(OPENCODE_PORT)/ 2>/dev/null || echo "  HTTP unreachable"
	@echo ""

opencode-web-restart:
	launchctl kickstart -k gui/$$(id -u)/$(OPENCODE_LABEL)

opencode-web-deploy:
	ansible-playbook $(MAC_SITE) --tags agents -e stayturgid_opencode_web_enabled=true
	@echo ""
	@-launchctl kickstart -k gui/$$(id -u)/$(OPENCODE_LABEL) 2>/dev/null
	@echo "OpenCode web deployed. Verify: make opencode-web-status"

opencode-web-disable:
	ansible-playbook $(MAC_SITE) --tags agents -e stayturgid_opencode_web_enabled=false

# ── SSH Certificate Authority ──────────────────────────────────────────────
CA_KEY := $(HOME)/.ssh/stayturgid_ca
CA_CERTDIR := $(HOME)/.ssh/host-certs

ca-status:
	@echo "SSH CA:"
	@[ -f "$(CA_KEY)" ] && ssh-keygen -lf "$(CA_KEY)" || echo "  CA key missing (run make ca-init)"
	@[ -f "$(CA_KEY).pub" ] && echo "  pub: $$(cat $(CA_KEY).pub | awk '{print $$3}')" || true
	@echo ""
	@-grep -c "cert-authority" ~/.ssh/known_hosts && echo "  entries in Mac known_hosts" || true
	@-for host in p7a hd8 s24; do \
	  ssh -o BatchMode=yes -o ConnectTimeout=5 $$host 'grep -c cert-authority ~/.ssh/known_hosts' 2>/dev/null \
	    && echo "  $$host known_hosts: ok" || echo "  $$host: unreachable"; \
	done
	@echo ""

ca-init:
	@[ -f "$(CA_KEY)" ] && echo "CA key already exists" || \
	  ssh-keygen -t ed25519 -f "$(CA_KEY)" -C "stayturgid-ca" -N ""
	@ssh-keygen -lf "$(CA_KEY)"
	@echo "@cert-authority * $$(cat $(CA_KEY).pub)" >> ~/.ssh/known_hosts \
	  && echo "Added @cert-authority to ~/.ssh/known_hosts" || true

ca-sign:
	@mkdir -p "$(CA_CERTDIR)"
	@ansible-playbook ansible/playbooks/fleet/termux-userland.yml --tags ca 2>&1 || true
	@echo "Host certs signed. Run 'make deploy-mac' to update Mac known_hosts."

# ── FIRERPA/lamda failsafe daemon ─────────────────────────────────────────
firerpa-deploy:
	ansible-playbook ansible/playbooks/fleet/firerpa.yml \
	  $(if $(HOSTS),-l "$(HOSTS)",) -e firerpa_enabled=true

firerpa-remove:
	ansible-playbook ansible/playbooks/fleet/firerpa.yml \
	  $(if $(HOSTS),-l "$(HOSTS)",) -e firerpa_enabled=false

firerpa-heal:
	python3 control/bin/firerpa_heal.py $(if $(HOSTS),--host $(HOSTS),--all)

collections:
	ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections

syntax:
	ansible-playbook ansible/playbooks/site.yml --syntax-check
	ansible-playbook $(MAC_SITE) --syntax-check
	ansible-playbook ansible/playbooks/fleet/termux-pkg-upgrade.yml --syntax-check

# Termux pkg update + full-upgrade on inventory hosts (same module as deploy).
# Nightly schedule: launchd com.stayturgid.termux-pkg-nightly (make deploy-mac).
termux-pkg-upgrade:
	python3 control/bin/termux_pkg_nightly.py $(if $(HOSTS),--limit "$(shell echo $(HOSTS) | tr ' ' ',')",)

# ------------------------------------------------------------------------------
# Device verification
# ------------------------------------------------------------------------------

verify device:
	bash tests/run.sh device $(HOSTS)

verify-heal:
	bash tests/run.sh device --heal $(HOSTS)

dryrun: deploy-check

dryrun-termux:
	ansible-playbook ansible/playbooks/fleet/termux-userland.yml --check --diff \
	  $(if $(HOSTS),--limit "$(HOSTS)",)

# ------------------------------------------------------------------------------
# Test & lint
# ------------------------------------------------------------------------------

all: test

configure:
	./configure

check:
	bash tests/run.sh code

unit:
	bash tests/run.sh unit

test: unit-and-pytest

unit-and-pytest:
	bash tests/run.sh local
	@$(MAKE) --no-print-directory pytest
	@$(MAKE) --no-print-directory ansible-test

test-venv $(VENV)/bin/pytest:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r tests/python/requirements.txt

pytest:
	@if [ -n "$(PYTEST)" ]; then \
	  echo "### pytest (Termux Python script twins)"; "$(PYTEST)"; \
	else \
	  echo "### pytest — SKIP (run 'make test-venv' to set up .venv-test)"; \
	fi

ansible-test:
	@if [ -n "$(ANSIBLE_TEST)" ]; then \
	  PYV=$$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")'); \
	  for c in $(COLLECTIONS); do \
	    echo "### ansible-test units (stayturgid.$$c)"; \
	    cd ansible_collections/stayturgid/$$c && "$(ANSIBLE_TEST)" units --local --python $$PYV || exit $$?; \
	    cd - >/dev/null; \
	  done; \
	else \
	  echo "### ansible-test — SKIP (run 'make test-venv')"; \
	fi

lint:
	ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections >/dev/null 2>&1 || true; \
	rc=0; \
	if command -v shellcheck >/dev/null; then shellcheck -S warning $$(git ls-files '*.sh') || rc=1; \
	else echo "shellcheck not installed (brew install shellcheck) — skipped"; fi; \
	if command -v ansible-lint >/dev/null; then \
	  bash -c 'cd ansible && ansible-lint playbooks/ ../ansible_collections/stayturgid/' || rc=1; \
	else echo "ansible-lint not installed (pipx install ansible-lint) — skipped"; fi; \
	if command -v yamllint >/dev/null; then yamllint ansible/ .ansible-lint .yamllint || rc=1; \
	else echo "yamllint not installed (pipx install yamllint) — skipped"; fi; \
	exit $$rc

clean:
	rm -f .config.mk
	rm -rf "$${TMPDIR:-/tmp}"/stayturgid-test.*
