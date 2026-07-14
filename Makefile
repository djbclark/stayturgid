# stayturgid — GNU Make compatibility shim.
# Primary interface: run `just` or `just --list`.
# This Makefile forwards to just; all substantive logic lives in the justfiles.
#
# Legacy invocation     Equivalent
#   make deploy HOSTS=s24  →  just deploy hosts=s24
#   make health            →  just health
#   make test              →  just test

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Pass HOSTS/SCOPE as env vars so `just` can use env_var_or_default.
export HOSTS ?=
export SCOPE ?= full

# ── Help ──────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo "stayturgid — common commands"
	@echo ""
	@echo "Primary interface:  just --list"
	@echo "Compatibility shim: make <target> → just <target>"
	@echo ""
	@echo "Variables:  HOSTS=s24   limit to inventory host(s)"
	@echo "            SCOPE=full  deploy scope: full | fdroid | play | app-stores"
	@echo ""
	@just --list

# ── Forwarding targets — one per recipe ───────────────────────────────────
# Pattern: each target maps directly to `just <target>` with no extra logic.

.PHONY: deploy deploy-check deploy-mac deploy-termux bootstrap-ssh \
        bootstrap-apks verify-bootstrap-apks ensure-shizuku \
        secretspec-check health errors ensure-et-mac check-et-mac \
        fix-hd8-google verify-play-autoupdate verify-hd8-google \
        collections syntax termux-pkg-upgrade \
        verify verify-heal device dryrun dryrun-termux \
        ca-init ca-sign ca-status \
        firerpa-deploy firerpa-remove firerpa-heal firerpa-health \
        verify-drift \
        hermes-start hermes-stop hermes-restart hermes-status hermes-status-full \
        hermes-logs hermes-logs-follow hermes-doctor hermes-deploy hermes-disable hermes-update \
        opencode-web-status opencode-web-restart opencode-web-deploy opencode-web-disable \
        dashboard-status dashboard-restart dashboard-deploy dashboard-disable dashboard-logs \
        landing-status landing-restart landing-deploy landing-disable landing-discover \
        vlm-install vlm-server vlm-check vlm-service-install vlm-service-status \
        vlm-service-stop vlm-service-restart vlm-smoke vlm-stop vlm-upstream-check \
        configure check unit pytest ansible-test test-venv test unit-and-pytest lint clean

deploy deploy-check deploy-mac deploy-termux bootstrap-ssh \
bootstrap-apks verify-bootstrap-apks ensure-shizuku \
secretspec-check health errors ensure-et-mac check-et-mac \
fix-hd8-google verify-play-autoupdate verify-hd8-google \
collections syntax termux-pkg-upgrade \
verify verify-heal device dryrun dryrun-termux \
ca-init ca-sign ca-status \
firerpa-deploy firerpa-remove firerpa-heal firerpa-health \
verify-drift \
hermes-start hermes-stop hermes-restart hermes-status hermes-status-full \
hermes-logs hermes-logs-follow hermes-doctor hermes-deploy hermes-disable hermes-update \
opencode-web-status opencode-web-restart opencode-web-deploy opencode-web-disable \
dashboard-status dashboard-restart dashboard-deploy dashboard-disable dashboard-logs \
landing-status landing-restart landing-deploy landing-disable landing-discover \
vlm-install vlm-server vlm-check vlm-service-install vlm-service-status \
vlm-service-stop vlm-service-restart vlm-smoke vlm-stop vlm-upstream-check \
configure check unit pytest ansible-test test-venv test unit-and-pytest lint clean:
	@just $@
