# Test & lint (no device required).

# Full test suite (default).
test: unit-and-pytest

# Report tool availability → .config.mk.
configure:
    ./configure

# Code-only syntax / import checks + ruff + typos + biome + shfmt + justfiles + markdown.
check:
    bash tests/run.sh code
    @just ruff
    @just typos
    @just biome
    @just shfmt
    @just just-check
    @just markdownlint
    @just prettier

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
      echo "### ansible-test — SKIP (run 'just test-venv')"; \
    fi

# Unit + pytest + ansible-test + ruff + typos + biome + shfmt + justfiles + markdown (CI default).
unit-and-pytest:
    bash tests/run.sh local
    @just pytest
    @just ansible-test
    @just ruff
    @just typos
    @just biome
    @just shfmt
    @just just-check
    @just markdownlint
    @just prettier

# ruff check + format (Python).
ruff:
    @if command -v ruff >/dev/null; then \
      echo "### ruff check"; ruff check .; \
      echo "### ruff format"; ruff format --check .; \
    else \
      echo "ruff not installed (brew install ruff) — skipped"; \
    fi

# biome check + format (JavaScript/AutoJs6).
biome:
    @if command -v biome >/dev/null; then \
      echo "### biome check"; biome check device/autojs6/; \
    else \
      echo "biome not installed (brew install biome) — skipped"; \
    fi

# shfmt diff (shell script format check).
shfmt:
    @if command -v shfmt >/dev/null; then \
      echo "### shfmt -d"; shfmt -d -i 2 -ci $(git ls-files '*.sh'); \
    else \
      echo "shfmt not installed (brew install shfmt) — skipped"; \
    fi

# markdownlint check (lint).
markdownlint:
    @if command -v markdownlint >/dev/null; then \
      echo "### markdownlint"; markdownlint --config .markdownlint.json $(git ls-files '*.md'); \
    else \
      echo "markdownlint not installed (brew install markdownlint-cli) — skipped"; \
    fi

# prettier check (format).
prettier:
    @if command -v prettier >/dev/null; then \
      echo "### prettier --check"; prettier --check $(git ls-files '*.md'); \
    else \
      echo "prettier not installed (brew install prettier) — skipped"; \
    fi

# Source-code spelling check.
typos:
    @if command -v typos >/dev/null; then \
      typos; \
    else \
      echo "typos not installed (brew install typos-cli) — skipped"; \
    fi

# shellcheck + ansible-lint + yamllint + ruff + typos + biome + shfmt + justfiles + markdown.
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
      echo "ansible-lint not installed (uv tool install ansible-lint) — skipped"
    fi
    if command -v yamllint >/dev/null; then
      yamllint ansible/ .ansible-lint .yamllint || rc=1
    else
      echo "yamllint not installed (uv tool install yamllint) — skipped"
    fi
    if command -v ruff >/dev/null; then
      ruff check . || rc=1
      ruff format --check . || rc=1
    else
      echo "ruff not installed (brew install ruff) — skipped"
    fi
    if command -v typos >/dev/null; then
      typos || rc=1
    else
      echo "typos not installed (brew install typos-cli) — skipped"
    fi
    if command -v biome >/dev/null; then
      biome ci device/autojs6/ || rc=1
    else
      echo "biome not installed (brew install biome) — skipped"
    fi
    if command -v shfmt >/dev/null; then
      shfmt -d -i 2 -ci $(git ls-files '*.sh') || rc=1
    else
      echo "shfmt not installed (brew install shfmt) — skipped"
    fi
    if command -v just >/dev/null; then
      just --fmt --check || rc=1
      echo "justfiles: fmt ok"
    else
      echo "just not installed (brew install just) — skipped"
    fi
    if command -v markdownlint >/dev/null; then
      markdownlint --config .markdownlint.json $(git ls-files '*.md') || rc=1
    else
      echo "markdownlint not installed (brew install markdownlint-cli) — skipped"
    fi
    if command -v prettier >/dev/null; then
      prettier --check $(git ls-files '*.md') || rc=1
    else
      echo "prettier not installed (brew install prettier) — skipped"
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
