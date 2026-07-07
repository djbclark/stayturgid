# stayturgid — test/verify entry points (GNU-style).
#   ./configure          optional: report tool availability
#   make check           tier (a) code-only checks (syntax under local interpreters)
#   make test            tiers (a)+(b): code checks + device-free unit tests + pytest + ansible-test
#   make pytest          plain-pytest tests for the Termux Python script twins
#   make ansible-test    official `ansible-test units` for the stayturgid.fleet module
#   make test-venv       create .venv-test with ansible-core + pytest + pytest-ansible
#   make verify          tier (c): read-only device checks over SSH
#   make dryrun          tier (c): Ansible --check --diff dry run against the fleet
#   make lint            shellcheck + ansible-lint + yamllint (whichever are installed)
#
# The same tiers are runnable directly (idiomatic TAP harness):
#   tests/run.sh [code|unit|local|device|all]
# and the Ansible-standard way:
#   ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook ansible/playbooks/termux-userland.yml --syntax-check
#   ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook ansible/playbooks/termux-userland.yml --check --diff

SHELL := /bin/bash
HOSTS ?=
VENV := .venv-test
COLLECTIONS := android_common termux obtainium fdroid play
# Prefer the project venv; fall back to any pytest/ansible-test on PATH.
PYTEST := $(shell [ -x $(VENV)/bin/pytest ] && echo $(VENV)/bin/pytest || command -v pytest)
ANSIBLE_TEST := $(shell [ -x $(VENV)/bin/ansible-test ] && echo $(abspath $(VENV))/bin/ansible-test || command -v ansible-test)
-include .config.mk

.PHONY: all check test unit pytest ansible-test test-venv verify device dryrun lint clean help

all: test

help:
	@grep -E '^#( |$$)' Makefile | sed 's/^# \{0,1\}//'

check:
	bash tests/run.sh code

unit:
	bash tests/run.sh unit

test: unit-and-pytest

# tier (b) shell TAP harness + Python twins (pytest) + module (ansible-test)
.PHONY: unit-and-pytest
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

# Official Ansible unit-test runner for stayturgid domain collections.
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

verify device:
	bash tests/run.sh device $(HOSTS)

dryrun:
	ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook \
	  ansible/playbooks/termux-userland.yml --check --diff \
	  $(if $(HOSTS),--limit "$(HOSTS)",)

lint:
	ANSIBLE_CONFIG=ansible/ansible.cfg ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections >/dev/null 2>&1 || true; \
	rc=0; \
	if command -v shellcheck >/dev/null; then shellcheck -S warning $$(git ls-files '*.sh') || rc=1; \
	else echo "shellcheck not installed (brew install shellcheck) — skipped"; fi; \
	if command -v ansible-lint >/dev/null; then \
	  ANSIBLE_CONFIG=ansible/ansible.cfg bash -c 'cd ansible && ansible-lint playbooks/ roles/' || rc=1; \
	else echo "ansible-lint not installed (pipx install ansible-lint) — skipped"; fi; \
	if command -v yamllint >/dev/null; then yamllint ansible/ .ansible-lint .yamllint || rc=1; \
	else echo "yamllint not installed (pipx install yamllint) — skipped"; fi; \
	exit $$rc

clean:
	rm -f .config.mk
	rm -rf "$${TMPDIR:-/tmp}"/stayturgid-test.*
