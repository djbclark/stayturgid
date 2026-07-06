# stayturgid — test/verify entry points (GNU-style).
#   ./configure          optional: report tool availability
#   make check           tier (a) code-only checks (syntax under local interpreters)
#   make test            tiers (a)+(b): code checks + device-free unit tests
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
-include .config.mk

.PHONY: all check test unit verify device dryrun lint clean help

all: test

help:
	@grep -E '^#( |$$)' Makefile | sed 's/^# \{0,1\}//'

check:
	bash tests/run.sh code

unit:
	bash tests/run.sh unit

test:
	bash tests/run.sh local

verify device:
	bash tests/run.sh device $(HOSTS)

dryrun:
	ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook \
	  ansible/playbooks/termux-userland.yml --check --diff \
	  $(if $(HOSTS),--limit "$(HOSTS)",)

lint:
	@rc=0; \
	if command -v shellcheck >/dev/null; then shellcheck -S warning $$(git ls-files '*.sh') || rc=1; \
	else echo "shellcheck not installed (brew install shellcheck) — skipped"; fi; \
	if command -v ansible-lint >/dev/null; then (cd ansible && ansible-lint playbooks/ roles/) || rc=1; \
	else echo "ansible-lint not installed (pipx install ansible-lint) — skipped"; fi; \
	if command -v yamllint >/dev/null; then yamllint ansible/ .ansible-lint .yamllint || rc=1; \
	else echo "yamllint not installed (pipx install yamllint) — skipped"; fi; \
	exit $$rc

clean:
	rm -f .config.mk
	rm -rf "$${TMPDIR:-/tmp}"/stayturgid-test.*
