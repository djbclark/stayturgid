# Test & lint (no device required).

# Full test suite (default).
test: unit-and-pytest

# Report tool availability → .config.mk.
configure:
    ./configure

# Code-only syntax / import checks + ruff.
check:
    bash tests/run.sh code
    @just ruff

# Device-free unit tests (shell TAP).
unit:
    bash tests/run.sh unit

# Python unit tests (Termux script twins).
pytest:
    @if [ -x "{{ venv }}/bin/pytest" ]; then \
      echo "### pytest (Termux Python script twins)"; "{{ venv }}/bin/pytest"; \
    else \
      echo "### pytest — SKIP (run 'just test-venv' to set up .venv-test)"; \
    fi

# Create .venv-test (once).
test-venv:
    uv venv {{ venv }}
    uv pip install --python {{ venv }}/bin/python -r tests/python/requirements.txt

# ansible-test units for collections.
ansible-test:
    @if [ -x "{{ venv }}/bin/ansible-test" ]; then \
      PYV="$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}')")"; \
      for c in {{ collections }}; do \
        echo "### ansible-test units (stayturgid.$$c)"; \
        cd ansible_collections/stayturgid/$$c && "{{ venv }}/bin/ansible-test" units --local --python $$PYV || exit $$?; \
        cd - >/dev/null; \
      done; \
    else \
      echo "### ansible-test — SKIP (run 'make test-venv')"; \
    fi

# Unit + pytest + ansible-test + ruff (CI default).
unit-and-pytest:
    bash tests/run.sh local
    @just pytest
    @just ansible-test
    @just ruff

# ruff check + format (Python).
ruff:
    @if command -v ruff >/dev/null; then \
      echo "### ruff check"; ruff check .; \
      echo "### ruff format"; ruff format --check .; \
    else \
      echo "ruff not installed (brew install ruff) — skipped"; \
    fi

# shellcheck + ansible-lint + yamllint + ruff.
lint:
    #!/usr/bin/env bash
    set -euo pipefail
    ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections >/dev/null 2>&1 || true
    rc=0
    if command -v shellcheck >/dev/null; then
      shellcheck -S warning $(git ls-files '*.sh') || rc=1
    else
      echo "shellcheck not installed (brew install shellcheck) — skipped"
    fi
    if command -v ansible-lint >/dev/null; then
      bash -c 'cd ansible && ansible-lint playbooks/ ../ansible_collections/stayturgid/' || rc=1
    else
      echo "ansible-lint not installed (pipx install ansible-lint) — skipped"
    fi
    if command -v yamllint >/dev/null; then
      yamllint ansible/ .ansible-lint .yamllint || rc=1
    else
      echo "yamllint not installed (pipx install yamllint) — skipped"
    fi
    if command -v ruff >/dev/null; then
      ruff check . || rc=1
      ruff format --check . || rc=1
    else
      echo "ruff not installed (brew install ruff) — skipped"
    fi
    exit $rc

# Remove temporary build + test artifacts.
clean:
    rm -f .config.mk
    rm -rf "$${TMPDIR:-/tmp}"/stayturgid-test.*

# ── Formatting check for justfiles ────────────────────────────────────────

# Verify all justfiles are valid and formatted.
just-check:
    @just --fmt --check
    @echo "justfiles: fmt ok"
    @just --list >/dev/null
    @echo "justfiles: parse ok"
