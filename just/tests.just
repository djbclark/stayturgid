# Test & lint (no device required).

# Full test suite (default).
test: unit-and-pytest

# Report tool availability → .config.mk.
configure:
    ./configure

# Code-only syntax / import checks + ruff + typos + biome + shfmt + justfiles + markdown.
check:
    bash tests/run.sh code
    @just site-contract-check
    @just ruff
    @just typos
    @just biome
    @just shfmt
    @just just-check
    @just markdownlint
    @just prettier
    @just html-validate
    @just stylelint
    @just validate-identity

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
    @if [ -x "{{ repo }}/{{ venv }}/bin/ansible-test" ]; then \
      PYV="$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')"; \
      for c in {{ collections }}; do \
        echo "### ansible-test units (stayturgid.$c)"; \
        cd ansible_collections/stayturgid/$c && "{{ repo }}/{{ venv }}/bin/ansible-test" units --local --python $PYV || exit $?; \
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
    @just html-validate
    @just stylelint
    @just validate-identity

# ruff check + format (Python).
ruff:
    @if command -v ruff >/dev/null; then \
      echo "### ruff check"; ruff check .; \
      echo "### ruff format"; ruff format --check .; \
    else \
      echo "ruff not installed (brew install ruff) — skipped"; \
    fi

# biome check + format (JavaScript/AutoJs6 + CSS).
biome:
    @if command -v biome >/dev/null; then \
      echo "### biome check"; biome check device/autojs6/ control/static/; \
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
      echo "### markdownlint"; markdownlint --config .markdownlint.json $(git ls-files '*.md' '*.md.example'); \
    else \
      echo "markdownlint not installed (brew install markdownlint-cli) — skipped"; \
    fi

# prettier check (format — markdown, HTML, CSS).
prettier:
    @if command -v prettier >/dev/null; then \
      echo "### prettier --check"; prettier --check $(git ls-files '*.md' '*.md.example' '*.html' '*.css' '*.toml' '*.ini'); \
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

# html-validate for HTML templates (strips Jinja before validation).
html-validate:
    @bash just/tools/html_validate.sh

# lychee — check links on the running fleet dashboard.
lychee:
    @if command -v lychee >/dev/null; then \
      echo "### lychee"; \
      if curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then \
        lychee --accept 100..=103,200..=299,500 http://127.0.0.1:4097/ http://127.0.0.1:4097/errors 2>&1 || true; \
        if curl -sf http://127.0.0.1:4097/stats >/dev/null 2>&1; then \
          lychee --accept 100..=103,200..=299,500 http://127.0.0.1:4097/stats 2>&1 || true; \
        fi; \
      else \
        echo "lychee — SKIP (dashboard not running on :4097)"; \
      fi; \
    else \
      echo "lychee not installed (brew install lychee) — skipped"; \
    fi

# lychee-docs — check markdown links offline.
lychee-docs:
    @if command -v lychee >/dev/null; then \
      echo "### lychee-docs"; \
      lychee --offline --exclude-path 'node_modules|\.html$' --root-dir . .; \
    else \
      echo "lychee not installed (brew install lychee) — skipped"; \
    fi


# Web health: validates rendered HTML and checks links on the running dashboard.
web-health:
    @echo "### web-health"
    @just html-validate
    @just lychee
    @just lighthouse
    @just pa11y
    @just puppeteer
    @just vnu

# stylelint for CSS.
stylelint:
    @if [ -d node_modules ]; then \
      echo "### stylelint"; \
      bunx stylelint --config .stylelintrc.json $(git ls-files '*.css') || exit 1; \
    else \
      echo "stylelint not available (bun install) — skipped"; \
    fi

# Lighthouse full-page audit (requires Chrome/Chromium on PATH).
lighthouse:
    @if command -v google-chrome >/dev/null || command -v chromium >/dev/null || [ -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then \
      echo "### lighthouse"; \
      if curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then \
        echo "lighthouse — SKIP (manual: bunx lighthouse http://127.0.0.1:4097/)"; \
      else \
        echo "lighthouse — SKIP (dashboard not running on :4097)"; \
      fi; \
    else \
      echo "lighthouse — SKIP (requires Chrome/Chromium)"; \
    fi

# VNU (Nu HTML Checker) — W3C validation of HTML templates.
vnu:
    @bash just/tools/vnu_validate.sh

# Pa11y accessibility audit on the running dashboard.
pa11y:
    @bash just/tools/pa11y_check.sh

# Puppeteer rendered-DOM check on the running dashboard.
puppeteer:
    @if [ -d node_modules ]; then \
      echo "### puppeteer"; \
      if curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then \
        node just/tools/rendered_dom_check.js || exit 1; \
      else \
        echo "puppeteer — SKIP (dashboard not running on :4097)"; \
      fi; \
    else \
      echo "puppeteer not available (bun install) — skipped"; \
    fi

# Same as lint but skip dashboard-dependent checks (lychee, vnu, pa11y, puppeteer).
lint-offline:
    STAYTURGID_LINT_OFFLINE=true just lint

# shellcheck + ansible-lint + yamllint + ruff + typos + biome + shfmt + justfiles + markdown + html-validate.
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
      for d in examples/consumer-*/; do
        (cd "$d" && ansible-lint playbook.yml) || rc=1
      done
    else
      echo "ansible-lint not installed (uv tool install ansible-lint) — skipped"
    fi
    if command -v yamllint >/dev/null; then
      yamllint ansible/ .ansible-lint .yamllint || rc=1
      yamllint -c .yamllint $(git ls-files '*.yml.example') || rc=1
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
      biome ci device/autojs6/ control/static/ || rc=1
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
      markdownlint --config .markdownlint.json $(git ls-files '*.md' '*.md.example') || rc=1
    else
      echo "markdownlint not installed (brew install markdownlint-cli) — skipped"
    fi
    if command -v prettier >/dev/null; then
      prettier --check $(git ls-files '*.md' '*.md.example' '*.html' '*.css' '*.toml' '*.ini') || rc=1
    else
      echo "prettier not installed (brew install prettier) — skipped"
    fi
    if command -v dotenv-linter >/dev/null; then
      dotenv-linter check $(git ls-files '.env' '*.env.example') || rc=1
    else
      echo "dotenv-linter not installed (brew install dotenv-linter) — skipped"
    fi
    if pyinilint_cmd="$(command -v pyinilint)" || [ -x "$HOME/.local/bin/pyinilint" ]; then
      pyinilint_cmd="${pyinilint_cmd:-$HOME/.local/bin/pyinilint}"
      echo "### pyinilint"
      "$pyinilint_cmd" $(git ls-files '*.ini') || rc=1
    else
      echo "pyinilint not installed (uv tool install pyinilint) — skipped"
    fi
    if command -v caddy >/dev/null; then
      if caddy fmt --diff control/caddy/Caddyfile | grep -q '^[+-]'; then
        echo "Caddyfile needs formatting — run caddy fmt --overwrite control/caddy/Caddyfile"
        rc=1
      fi
    else
      echo "caddy not installed (brew install caddy) — skipped"
    fi
    bash just/tools/html_validate.sh || rc=1
    if [ -z "${STAYTURGID_LINT_OFFLINE:-}" ]; then
      bash just/tools/vnu_validate.sh || rc=1
    fi
    if [ -d node_modules ]; then
      echo "### stylelint"
      bunx stylelint --config .stylelintrc.json $(git ls-files '*.css') || rc=1
    else
      echo "stylelint not available (bun install) — skipped"
    fi
    if command -v lychee >/dev/null; then
      echo "### lychee-docs"
      lychee --offline --exclude-path 'node_modules|\.html$' --root-dir . . || rc=1
    else
      echo "lychee not installed (brew install lychee) — skipped"
    fi
    if [ -n "${STAYTURGID_LINT_OFFLINE:-}" ]; then
      echo "lychee (dashboard) — SKIP (offline mode)"
    elif command -v lychee >/dev/null; then
      echo "### lychee (dashboard)"
      if curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then
        lychee --accept 100..=103,200..=299,500 http://127.0.0.1:4097/ http://127.0.0.1:4097/errors 2>&1 || rc=1
        if curl -sf http://127.0.0.1:4097/stats >/dev/null 2>&1; then
          lychee --accept 100..=103,200..=299,500 http://127.0.0.1:4097/stats 2>&1 || rc=1
        fi
      else
        echo "lychee (dashboard) — SKIP (dashboard not running on :4097)"
      fi
    fi
    if [ -z "${STAYTURGID_LINT_OFFLINE:-}" ] && [ -d node_modules ]; then
      echo "### pa11y"
      curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1 && bash just/tools/pa11y_check.sh || echo "pa11y — SKIP (dashboard not running on :4097)"
      echo "### puppeteer"
      if curl -sf http://127.0.0.1:4097/ >/dev/null 2>&1; then
        node just/tools/rendered_dom_check.js || rc=1
      else
        echo "puppeteer — SKIP (dashboard not running on :4097)"
      fi
    fi
    # validate-identity (hard-fail: no production identity outside site inventory)
    python3 control/bin/validate_site_identity.py --check-drift --check-secrets 2>&1 || rc=1
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

# Validate site identity: parse inventory; hard-fail on drift or secrets.
validate-identity:
    @echo "### validate-identity"
    @python3 control/bin/validate_site_identity.py --check-drift --check-secrets

# Alias kept for older docs/scripts; same as validate-identity.
validate-identity-strict:
    @echo "### validate-identity-strict"
    @python3 control/bin/validate_site_identity.py --check-drift --check-secrets

