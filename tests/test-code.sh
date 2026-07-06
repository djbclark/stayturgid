#!/usr/bin/env bash
# Tier (a): code-only checks — catches syntax breakage under the local
# interpreter versions (bash, python, node, ansible). No device, no network.
set -u
cd "$(dirname "$0")/.." || exit 2
. tests/lib.sh

echo "# interpreters: bash $BASH_VERSION | $(python3 -V 2>&1) | node $(node -v 2>/dev/null || echo none) | $(ansible-playbook --version 2>/dev/null | head -1 || echo 'ansible none')"

# --- bash syntax -----------------------------------------------------------
bad=""
for f in $(git ls-files '*.sh'); do
    bash -n "$f" 2>/dev/null || bad="$bad $f"
done
[ -z "$bad" ] && tap_ok "bash -n: all shell scripts parse" \
              || tap_fail "bash -n: all shell scripts parse" "failed:$bad"

# --- python ----------------------------------------------------------------
if python3 -m py_compile ansible/library/termux_pkg.py 2>/dev/null; then
    tap_ok "py_compile: ansible/library/termux_pkg.py"
else
    tap_fail "py_compile: ansible/library/termux_pkg.py"
fi

# --- javascript ------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
    bad=""
    for f in $(git ls-files 'autojs6/*.js' 'autojs6/**/*.js'); do
        node --check "$f" 2>/dev/null || bad="$bad $f"
    done
    [ -z "$bad" ] && tap_ok "node --check: all AutoJs6 sources parse" \
                  || tap_fail "node --check: all AutoJs6 sources parse" "failed:$bad"
else
    tap_skip "node --check: all AutoJs6 sources parse" "node not installed"
fi

# --- json ------------------------------------------------------------------
bad=""
for f in $(git ls-files '*.json'); do
    python3 -m json.tool "$f" >/dev/null 2>&1 || bad="$bad $f"
done
[ -z "$bad" ] && tap_ok "json: all catalogs/configs valid" \
              || tap_fail "json: all catalogs/configs valid" "failed:$bad"

# --- launchd plists (macOS only) -------------------------------------------
if command -v plutil >/dev/null 2>&1; then
    bad=""
    for f in $(git ls-files '*.plist'); do
        plutil -lint "$f" >/dev/null 2>&1 || bad="$bad $f"
    done
    [ -z "$bad" ] && tap_ok "plutil -lint: launchd plists valid" \
                  || tap_fail "plutil -lint: launchd plists valid" "failed:$bad"
else
    tap_skip "plutil -lint: launchd plists valid" "not macOS"
fi

# --- ansible ---------------------------------------------------------------
if command -v ansible-playbook >/dev/null 2>&1; then
    if ANSIBLE_CONFIG=ansible/ansible.cfg \
       ansible-playbook ansible/playbooks/termux-userland.yml --syntax-check >/dev/null 2>&1; then
        tap_ok "ansible-playbook --syntax-check: termux-userland.yml"
    else
        tap_fail "ansible-playbook --syntax-check: termux-userland.yml"
    fi
else
    tap_skip "ansible-playbook --syntax-check" "ansible not installed"
fi

# --- optional linters (run when installed, skip otherwise) ------------------
if command -v shellcheck >/dev/null 2>&1; then
    if shellcheck -S warning $(git ls-files '*.sh') >/dev/null 2>&1; then
        tap_ok "shellcheck -S warning: clean"
    else
        tap_fail "shellcheck -S warning: clean" "run: make lint"
    fi
else
    tap_skip "shellcheck" "not installed (brew install shellcheck)"
fi
if command -v ansible-lint >/dev/null 2>&1; then
    if (cd ansible && ansible-lint -q playbooks/ roles/ >/dev/null 2>&1); then
        tap_ok "ansible-lint: clean"
    else
        tap_fail "ansible-lint: clean" "run: make lint"
    fi
else
    tap_skip "ansible-lint" "not installed (pipx install ansible-lint)"
fi
if command -v yamllint >/dev/null 2>&1; then
    if yamllint -s ansible/ >/dev/null 2>&1; then
        tap_ok "yamllint: clean"
    else
        tap_fail "yamllint: clean" "run: make lint"
    fi
else
    tap_skip "yamllint" "not installed (pipx install yamllint)"
fi

tap_done
