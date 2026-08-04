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
    @just check-ts
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

# Bootstrap per-worktree dependencies (.venv-test, node_modules, .ansible/collections).
worktree-setup:
    @just test-venv
    @if command -v bun >/dev/null 2>&1; then \
      echo "### bun install"; bun install; \
    elif command -v npm >/dev/null 2>&1; then \
      echo "### npm install"; PUPPETEER_SKIP_DOWNLOAD=1 npm install; \
    else \
      echo "neither bun nor npm installed — skipping node_modules setup"; \
    fi
    @if command -v ansible-galaxy >/dev/null 2>&1; then \
      echo "### ansible-galaxy collections"; ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections --force; \
    fi

# Create .venv-test (once).
test-venv:
    @if [ ! -d "{{ venv }}" ]; then uv venv {{ venv }}; fi
    uv pip install --python {{ venv }}/bin/python -r tests/python/requirements.txt

# ansible-test units for collections.
ansible-test:
    @if [ -x "{{ repo }}/{{ venv }}/bin/ansible-test" ]; then \
      for c in {{ collections }}; do \
        echo "### ansible-test units (stayturgid.$c)"; \
        cd ansible_collections/stayturgid/$c && "{{ repo }}/{{ venv }}/bin/ansible-test" units --local --python-interpreter "{{ repo }}/{{ venv }}/bin/python" || exit $?; \
        cd - >/dev/null; \
      done; \
    else \
      echo "### ansible-test — SKIP (run 'just test-venv')"; \
    fi

# Install the exact dependency lock when the cached manifests do not match it.
_ensure-test-collections:
    @if ! python3 -c 'import json, pathlib, re, sys; root = pathlib.Path(".ansible/collections/ansible_collections"); locks = dict(re.findall(r"- name: ([^ ]+)\n[ ]+version: \"([^\"]+)\"", pathlib.Path("ansible/requirements.yml").read_text())); actual = {name: json.loads((root.joinpath(*name.split(".")) / "MANIFEST.json").read_text())["collection_info"]["version"] for name in locks}; sys.exit(0 if locks and actual == locks else 1)' 2>/dev/null; then \
      ansible-galaxy collection install --force -r ansible/requirements.yml -p .ansible/collections; \
    fi

# Unit + pytest + ansible-test + ruff + typos + biome + shfmt + justfiles + markdown (CI default).
unit-and-pytest: _ensure-test-collections
    bash tests/run.sh local
    @just pytest
    @just ansible-test
    @just check-ts
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

# biome check + format (JavaScript research tooling + CSS).
biome:
    @if command -v biome >/dev/null; then \
      echo "### biome check"; biome check control/static/; \
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
    @if [ ! -d node_modules ]; then \
      echo "prettier — SKIP (node_modules missing — run 'just worktree-setup')"; \
    elif command -v prettier >/dev/null; then \
      echo "### prettier --check"; prettier --check $(git ls-files '*.md' '*.md.example' '*.html' '*.css' '*.toml' '*.ini' | while read -r f; do [ -L "$f" ] || printf '%s\n' "$f"; done); \
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
lint: _ensure-test-collections
    #!/usr/bin/env bash
    set -euo pipefail
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
    if command -v mypy >/dev/null; then
      echo "### mypy"
      mypy control/ device/termux/py/ ansible_collections/ tests/ just/tools/ || rc=1
    else
      echo "mypy not installed (uv tool install mypy) — skipped"
    fi
    if command -v typos >/dev/null; then
      typos || rc=1
    else
      echo "typos not installed (brew install typos-cli) — skipped"
    fi
    if command -v biome >/dev/null; then
      biome ci control/static/ || rc=1
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
    if [ ! -d node_modules ]; then
      echo "prettier — SKIP (node_modules missing — run 'just worktree-setup')"
    elif command -v prettier >/dev/null; then
      prettier --check $(git ls-files '*.md' '*.md.example' '*.html' '*.css' '*.toml' '*.ini' | while read -r f; do [ -L "$f" ] || printf '%s\n' "$f"; done) || rc=1
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
    @STAYTURGID_SITE_DIR="${STAYTURGID_SITE_DIR:-ansible}" python3 control/bin/validate_site_identity.py --check-drift --check-secrets

# Alias kept for older docs/scripts; same as validate-identity.
validate-identity-strict:
    @echo "### validate-identity-strict"
    @STAYTURGID_SITE_DIR="${STAYTURGID_SITE_DIR:-ansible}" python3 control/bin/validate_site_identity.py --check-drift --check-secrets

# ── Native agent (OPTIONS K1 Phase 1) ─────────────────────────────────────

# Assemble stayturgid-agent debug APK (device/native-agent).
# composite=false uses Maven Central instead of ~/src/Shizuku/api.
# Prefers Homebrew OpenJDK 21 if present (AGP rejects JDK 25+).
agent-assemble composite="true":
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ repo }}/device/native-agent"
    if [[ -z "${JAVA_HOME:-}" ]]; then
      for cand in \
        /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
        /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home; do
        if [[ -x "$cand/bin/java" ]]; then
          export JAVA_HOME="$cand"
          break
        fi
      done
    fi
    if [[ ! -f local.properties ]]; then
      sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
      if [[ -d "$sdk" ]]; then
        echo "sdk.dir=$sdk" > local.properties
      fi
    fi
    props=()
    if [[ "{{ composite }}" == "false" ]]; then
      props+=(-Pshizuku.composite=false)
    fi
    ./gradlew --no-daemon "${props[@]}" :app:assembleDebug
    echo "APK: {{ repo }}/device/native-agent/app/build/outputs/apk/debug/app-debug.apk"

# Install debug APK via adb. Positional serial/host optional.
# Example: just agent-install 100.65.230.108:5555
agent-install target="":
    #!/usr/bin/env bash
    set -euo pipefail
    apk="{{ repo }}/device/native-agent/app/build/outputs/apk/debug/app-debug.apk"
    if [[ ! -f "$apk" ]]; then
      just agent-assemble
    fi
    keep="org.stayturgid.agent.debug"
    other="org.stayturgid.agent"
    adbcmd=(adb)
    if [[ -n "{{ target }}" ]]; then
      adbcmd=(adb -s "{{ target }}")
    fi
    # One agent per device: the debug and release builds have different
    # applicationIds and install side by side (each runs its own foreground
    # service). Remove the other build + stop old processes before installing.
    if "${adbcmd[@]}" shell pm path "$other" 2>/dev/null | grep -q package:; then
      echo "removing conflicting agent build $other (force-stop + uninstall)"
      "${adbcmd[@]}" shell am force-stop "$other" || true
      "${adbcmd[@]}" shell pm uninstall "$other" || true
    fi
    "${adbcmd[@]}" shell am force-stop "$keep" || true
    "${adbcmd[@]}" install -r "$apk"

# Ensure only one agent build is installed (removes the release build if the
# debug build is the keeper). Fixes/audits duplicate "UserService bound"
# notifications. Example: just agent-dedupe s24   (omit target for default device)
agent-dedupe target="":
    #!/usr/bin/env bash
    set -euo pipefail
    other="org.stayturgid.agent"
    adbcmd=(adb)
    if [[ -n "{{ target }}" ]]; then
      adbcmd=(adb -s "{{ target }}")
    fi
    if "${adbcmd[@]}" shell pm path "$other" 2>/dev/null | grep -q package:; then
      echo "removing conflicting agent build $other (force-stop + uninstall)"
      "${adbcmd[@]}" shell am force-stop "$other" || true
      "${adbcmd[@]}" shell pm uninstall "$other"
    else
      echo "OK: no conflicting agent build present (single agent)"
    fi

# Grant Shizuku to debug agent package (pm + shizuku.json).
# Example: just agent-grant 100.65.230.108:5555
agent-grant target:
    python3 "{{ repo }}/control/tools/native-agent/grant_shizuku.py" "{{ target }}"

# Launch MainActivity → HostService (app context FGS).
# Example: just agent-start stock-android-device
agent-start target:
    python3 "{{ repo }}/control/tools/native-agent/start_agent.py" "{{ target }}"

# Install + grant + start native-agent on reachable hosts (dual-run; leaves AutoJs6).
# Example: just agent-rollout
#          just agent-rollout p7a s24
agent-rollout +hosts="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -z "{{ hosts }}" ]]; then
      python3 "{{ repo }}/control/tools/native-agent/rollout.py"
    else
      # shell-split host list
      # shellcheck disable=SC2086
      python3 "{{ repo }}/control/tools/native-agent/rollout.py" {{ hosts }}
    fi

# Assign Fire-OS peer-start target(s) to a healthy peer (issue #61).
# Example: just agent-peer-provision s24 100.124.55.39:5555
agent-peer-provision peer +targets:
    #!/usr/bin/env bash
    set -euo pipefail
    # shellcheck disable=SC2086
    python3 "{{ repo }}/control/tools/native-agent/provision_peer.py" "{{ peer }}" {{ targets }}

# Trigger a peer-start now on a peer (watch the TARGET for the one-time Allow).
# Example: just agent-peer-start s24
agent-peer-start peer:
    python3 "{{ repo }}/control/tools/native-agent/provision_peer.py" "{{ peer }}" --start

# Show a peer's current peer.json + recent peerstart.log.
# Example: just agent-peer-show s24
agent-peer-show peer:
    python3 "{{ repo }}/control/tools/native-agent/provision_peer.py" "{{ peer }}" --show
