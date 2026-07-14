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
  [ -f "$f" ] || continue
  bash -n "$f" 2>/dev/null || bad="$bad $f"
done
[ -z "$bad" ] && tap_ok "bash -n: all shell scripts parse" ||
  tap_fail "bash -n: all shell scripts parse" "failed:$bad"

# --- python ----------------------------------------------------------------
PY_SRCS="$(git ls-files '*.py')"
if echo "$PY_SRCS" | xargs python3 -m py_compile 2>/dev/null; then
  tap_ok "py_compile: all Python sources"
else
  tap_fail "py_compile: all Python sources"
fi

# --- javascript ------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
  bad=""
  for f in $(git ls-files 'device/autojs6/*.js' 'device/autojs6/**/*.js'); do
    node --check "$f" 2>/dev/null || bad="$bad $f"
  done
  [ -z "$bad" ] && tap_ok "node --check: all AutoJs6 sources parse" ||
    tap_fail "node --check: all AutoJs6 sources parse" "failed:$bad"
else
  tap_skip "node --check: all AutoJs6 sources parse" "node not installed"
fi

# --- host-side AutoJs6 quality tooling (Biome) ----------------------------
if command -v biome >/dev/null 2>&1; then
  if biome check device/autojs6 >/dev/null 2>&1; then
    tap_ok "biome: AutoJs6 sources clean"
  else
    tap_fail "biome: AutoJs6 sources clean" "run: npm run lint:autojs6"
  fi
else
  tap_skip "biome: AutoJs6 sources clean" "biome not installed (brew install biome)"
fi

# --- shell script formatting (shfmt) --------------------------------------
if command -v shfmt >/dev/null 2>&1; then
  shell_files=()
  while IFS= read -r -d '' f; do
    [ -f "$f" ] && shell_files+=("$f")
  done < <(git ls-files -z '*.sh')
  if [ "${#shell_files[@]}" -eq 0 ] || shfmt -d -i 2 -ci "${shell_files[@]}" >/dev/null 2>&1; then
    tap_ok "shfmt: shell scripts formatted"
  else
    tap_fail "shfmt: shell scripts formatted" "run: shfmt -w -i 2 -ci <file>"
  fi
else
  tap_skip "shfmt: shell scripts formatted" "not installed (brew install shfmt)"
fi

# --- json ------------------------------------------------------------------
bad=""
for f in $(git ls-files '*.json'); do
  python3 -m json.tool "$f" >/dev/null 2>&1 || bad="$bad $f"
done
[ -z "$bad" ] && tap_ok "json: all catalogs/configs valid" ||
  tap_fail "json: all catalogs/configs valid" "failed:$bad"

# --- CFEngine standalone policy sources ------------------------------------
if command -v cf-promises >/dev/null 2>&1; then
  if cf-promises -f "$PWD/device/termux/cfengine/policy/stayturgid.cf" >/dev/null 2>&1 &&
    cf-promises -f "$PWD/device/termux/cfengine/policy/cf-serverd.cf" >/dev/null 2>&1; then
    tap_ok "cf-promises: standalone CFEngine policy sources parse"
  else
    tap_fail "cf-promises: standalone CFEngine policy sources parse"
  fi
else
  tap_skip "cf-promises: standalone CFEngine policy sources parse" "cfengine not installed (brew install cfengine)"
fi

# --- healing coverage check -------------------------------------------------
if python3 tests/check_healing_coverage.py --summary; then
  tap_ok "healing coverage: all must_cover IDs declared across mechanisms"
else
  tap_fail "healing coverage: gaps found — run 'python3 tests/check_healing_coverage.py' for details"
fi

# --- launchd plists (macOS only) -------------------------------------------
if command -v plutil >/dev/null 2>&1; then
  bad=""
  for f in $(git ls-files '*.plist'); do
    plutil -lint "$f" >/dev/null 2>&1 || bad="$bad $f"
  done
  [ -z "$bad" ] && tap_ok "plutil -lint: launchd plists valid" ||
    tap_fail "plutil -lint: launchd plists valid" "failed:$bad"
else
  tap_skip "plutil -lint: launchd plists valid" "not macOS"
fi

# --- ansible ---------------------------------------------------------------
if command -v ansible-playbook >/dev/null 2>&1; then
  for pb in ansible/playbooks/site.yml ansible/playbooks/control_node/site.yml ansible/playbooks/fleet/termux-userland.yml ansible/playbooks/fleet/bootstrap.yml; do
    if ANSIBLE_CONFIG=ansible/ansible.cfg \
      ansible-playbook "$pb" --syntax-check >/dev/null 2>&1; then
      tap_ok "ansible-playbook --syntax-check: $(basename "$pb")"
    else
      tap_fail "ansible-playbook --syntax-check: $(basename "$pb")"
    fi
  done
else
  tap_skip "ansible-playbook --syntax-check" "ansible not installed"
fi

# --- optional linters (run when installed, skip otherwise) ------------------
if command -v shellcheck >/dev/null 2>&1; then
  shell_files=()
  while IFS= read -r -d '' f; do
    [ -f "$f" ] && shell_files+=("$f")
  done < <(git ls-files -z '*.sh')
  if [ "${#shell_files[@]}" -eq 0 ] || shellcheck -S warning "${shell_files[@]}" >/dev/null 2>&1; then
    tap_ok "shellcheck -S warning: clean"
  else
    tap_fail "shellcheck -S warning: clean" "run: just lint"
  fi
else
  tap_skip "shellcheck" "not installed (brew install shellcheck)"
fi
if command -v ansible-lint >/dev/null 2>&1; then
  if ANSIBLE_CONFIG=ansible/ansible.cfg bash -c \
    'cd ansible && ansible-lint -q playbooks/ ../ansible_collections/stayturgid/' \
    >/dev/null 2>&1; then
    tap_ok "ansible-lint: clean"
  else
    tap_fail "ansible-lint: clean" "run: just lint"
  fi
else
  tap_skip "ansible-lint" "not installed (pipx install ansible-lint)"
fi
if command -v yamllint >/dev/null 2>&1; then
  if yamllint -s ansible/ >/dev/null 2>&1; then
    tap_ok "yamllint: clean"
  else
    tap_fail "yamllint: clean" "run: just lint"
  fi
else
  tap_skip "yamllint" "not installed (pipx install yamllint)"
fi

# --- justfiles -------------------------------------------------------------
if command -v just >/dev/null 2>&1; then
  if just --justfile examples/firerpa-nonroot/justfile --fmt --check >/dev/null 2>&1; then
    tap_ok "just --fmt --check: standalone FIRERPA justfile"
  else
    tap_fail "just --fmt --check: standalone FIRERPA justfile"
  fi
else
  tap_skip "justfile format/parse" "just not installed (brew install just)"
fi

# Python test collection — catches import/syntax breakage in the pytest layer
# even when the full run happens via `just pytest`.
PYTEST_BIN="$([ -x .venv-test/bin/pytest ] && echo .venv-test/bin/pytest || command -v pytest || true)"
if [ -n "$PYTEST_BIN" ]; then
  if "$PYTEST_BIN" --collect-only -q >/dev/null 2>&1; then
    tap_ok "pytest: tests collect cleanly"
  else
    tap_fail "pytest: tests collect cleanly" "run: just pytest"
  fi
else
  tap_skip "pytest collect" "no pytest (run: just test-venv)"
fi

tap_done
