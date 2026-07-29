# stayturgid — operator commands (run `just` or `just --list`).
#
# Variables (optional on most recipes):
#   hosts=oneui-device       Limit to one or more inventory hosts: just deploy hosts=oneui-device fireos-device
#   scope=full      Deploy scope: full | fdroid | play | app-stores
#   devices_only=1  Skip the Mac control_node pass (#57) — for iterating on one device
#
# Quick start:
#   just help           → show this listing
#   just check          → syntax / import checks
#   just test           → full test suite
#   just --set hosts oneui-device deploy  → fleet deploy

set shell := ["bash", "-uc"]

repo := justfile_directory()
export STAYTURGID_ROOT := repo
ansible_playbook := "python3 control/bin/ansible_exec.py ansible-playbook"

hosts := env_var_or_default("hosts", "")
scope := env_var_or_default("scope", "full")
devices_only := env_var_or_default("devices_only", "")

deploy_args := env_var_or_default("deploy_args", if hosts == "" { "" } else { hosts })
deploy_scope_arg := env_var_or_default("deploy_scope_arg", if scope == "full" { "" } else { "--scope " + scope })
deploy_devices_only_arg := env_var_or_default("deploy_devices_only_arg", if devices_only == "" { "" } else { "--devices-only" })
limit_flag := env_var_or_default("limit_flag", if hosts == "" { "" } else { "-l " + hosts })

mac_site := "ansible/playbooks/control_node/site.yml"
venv := ".venv-test"
collections := "android_common termux obtainium fdroid play"

import "just/fleet.just"
import "just/kotlin.just"
import "just/services.just"
import "just/tests.just"
import "just/cfengine.just"
import "just/site.just"
import "just/vendor.just"

# Show available recipes (default).
help:
    @just --justfile "{{ repo }}/justfile" --list

# Run AI-powered code review on staged changes (via Alibaba Open Code Review)
ocr *args:
    bunx ocr review {{ args }}

# Run AI-powered file scan (via Alibaba Open Code Review)
ocr-scan *args:
    bunx ocr scan {{ args }}

# Generate a prompt and diff for Antigravity to review directly
agent-review:
    @echo "Hey Antigravity, please act as an expert senior staff engineer and perform a deep code review on the following diff."
    @echo "Focus on:"
    @echo "1. Logic bugs, race conditions, and edge cases"
    @echo "2. Security vulnerabilities (e.g. injection, permissions)"
    @echo "3. Maintainability, readability, and DRY principles"
    @echo "4. Do not nitpick stylistic choices unless they violate the project's established patterns."
    @echo ""
    @echo '```diff'
    @git diff HEAD
    @echo '```'

# Build TypeScript files into JavaScript and add generated header
build-ts:
    bunx tsc -p device/autojs6/tsconfig.json
    bunx tsc -p docs/research/autojs6-hd8-project/tsconfig.json
    bunx tsc -p tests/js/tsconfig.json
    bunx tsc -p just/tools/tsconfig.json
    bunx biome format --write device/autojs6 tests/js just/tools docs/research
    python3 just/tools/add_generated_header.py

# Verify TS/JS migration and mappings
check-ts:
    @echo "Verifying 1-to-1 mapping..."
    @for f in $(find device/autojs6 tests/js just/tools docs/research -name "*.ts" -not -name "*.d.ts" -not -path "*/node_modules/*" 2>/dev/null); do \
      js_file="${f%.ts}.js"; \
      if [ ! -f "$js_file" ]; then \
        echo "Error: Missing corresponding JS file for $f (run 'just build-ts')"; exit 1; \
      fi \
    done
    @echo "Verifying no stray JS files..."
    @for f in $(find device/autojs6 tests/js just/tools docs/research -name "*.js" -not -path "*/node_modules/*" 2>/dev/null); do \
      ts_file="${f%.js}.ts"; \
      if [ ! -f "$ts_file" ]; then \
        echo "Error: Stray JS file with no corresponding TS source: $f"; exit 1; \
      fi \
    done
    @echo "Verifying generated headers..."
    @python3 just/tools/add_generated_header.py --check
