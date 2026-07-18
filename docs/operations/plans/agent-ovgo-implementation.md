<!-- historical: production hostnames/IPs in this file are session records; see docs/architecture/multi-site-topology.md §4.1 for current example names -->

# O-V-G-O Stack & Site Identity Implementation Plan (Agent Instructions)

**Audience:** Junior Developer / Autonomous AI Agent
**Context:** This document provides explicit, step-by-step instructions to implement the unified architecture outlined in [docs/architecture/core-architecture.md](file:///Users/djbclark/ops/stayturgid/docs/architecture/core-architecture.md).
**End Goal:** Completely replace the legacy custom Python dashboard (`dashboard.py`) and polling monitors (`fleet_health_monitor.py`, `access_monitor.py`) with a modern, resilient, push-based telemetry stack (Vector) and a clean OliveTin execution interface. All configuration must be generated from the Ansible site inventory.

---

## Agent Guidelines & Rules

1. **Check Before You Edit:** Always use `view_file` or `grep_search` to understand the current context of a file before modifying it.
2. **Read Required Context:** You must review [docs/coding-rules.md](file:///Users/djbclark/ops/stayturgid/docs/coding-rules.md), [AGENTS.md](file:///Users/djbclark/ops/stayturgid/AGENTS.md), and [docs/handoff.md](file:///Users/djbclark/ops/stayturgid/docs/handoff.md) to understand project conventions and current session state before starting work.
3. **Do Not Hallucinate Paths:** All file paths must be exact. Refer to the directory structure using the `list_dir` tool if you are unsure.
4. **Run Verifications Locally:** Use the `just check`, `just lint`, and `just test` commands heavily to catch regressions. If a test fails, you must revert or fix the error before proceeding.
5. **Multi-Agent Protocol:** Before making any edits, run `git fetch origin --prune && git pull --ff-only origin master`. When a phase is complete and passes tests, commit your work with a clear message and push.

---

## Step-by-Step Execution Plan

### Phase 1: Establish the Identity Validator

_Your goal is to build the strict validator for the Ansible site inventory._

1. **Create the Validator Script:**
   - **Path:** `control/bin/validate_site_identity.py`
   - **Action:** Write a Python script that loads Ansible inventory JSON (`ansible-inventory -i ansible/inventory/hosts.yml --list`) and enforces that required fields (e.g., `device_usb_serial`, `ansible_host`) are present and valid.
2. **Integrate with `just`:**
   - **Action:** Add a `validate-identity` recipe to the root `justfile` that runs this script.

**Verification:** Run `just validate-identity`. Ensure it passes against the current `ansible/inventory/hosts.yml`.

### Phase 2: Deprecate Legacy Monitors and Dashboard

_Your goal is to surgically remove the legacy Mac polling scripts and the Flask dashboard._

1. **Remove Python Scripts:**
   - **Target Files:** `control/bin/dashboard.py`, `control/bin/fleet_health_monitor.py`, `control/bin/access_monitor.py`
   - **Action:** Delete these files.
2. **Remove Launchd Plists:**
   - **Target Files:** `ansible/roles/control_node/templates/dashboard.plist.j2`, `ansible/roles/control_node/templates/fleet-health.plist.j2`, `ansible/roles/control_node/templates/access-monitor.plist.j2`
   - **Action:** Delete these files.
3. **Update Ansible Tasks (`ansible/roles/control_node/tasks/agents.yml`):**
   - **Action:** Search for the tasks that render, remove, or unload the plists for `dashboard`, `fleet-health`, and `access-monitor`. Remove these blocks entirely.
4. **Update `justfile` & `just/fleet.just`:**
   - **Action:** Remove recipes that explicitly call the deleted scripts, such as `just health` and `just errors`.

**Verification:** Run `just check` and `just lint`. Ensure no broken imports or missing file errors occur.

### Phase 3: Implement Vector on the Edge (Ansible)

_Your goal is to configure the Android Termux environment to run Vector natively._

1. **Locate the Termux Userland Role:**
   - **Path:** `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml`
2. **Add Vector Download Task:**
   - **Action:** Add a task using `ansible.builtin.get_url` (or `unarchive`) to download the `vector-X.Y.Z-aarch64-unknown-linux-musl.tar.gz` release from GitHub directly into `/data/data/com.termux/files/usr/bin/vector`.
3. **Configure Vector (`vector.toml`):**
   - **Action:** Create a template `vector.toml.j2` in the role's `templates` directory. Define a `[sources.battery]` exec source and a `[sources.logcat]` file source.
4. **Set up Termux-Services Boot Hook:**
   - **Action:** Add an Ansible task to create a `termux-services` run script for Vector so it starts automatically.

**Verification:** Run `just dryrun-termux` to ensure your new Ansible tasks pass syntax and dry-run checks.

### Phase 4: Draft the OliveTin Configuration

_Your goal is to create the operational interface configuration that replaces the `just` CLI usage._

1. **Create the Config File Template:**
   - **Path:** `ansible/roles/control_node/templates/olivetin-config.yaml.j2`
2. **Define Actions (Buttons):**
   - **Action:** Write YAML defining OliveTin actions. Iterate over the Ansible inventory (`groups['stayturgid']`) to generate buttons dynamically for each device.
3. **Ensure Environment Propagation:**
   - **Critical Instruction:** OliveTin runs commands in a clean shell. You **must** ensure the `shell` command explicitly sources the Mac environment.
   - **Example:**
     ```yaml
     actions:
       - title: Deploy Specific Host
         icon: "&#128640;"
         shell: |
           export PATH="/opt/homebrew/bin:$PATH"
           export STAYTURGID_ADB="/opt/homebrew/bin/adb"
           cd {{ stayturgid_repo_root }} && just --set hosts {{ item }} deploy
     ```
4. **Deploy OliveTin via Ansible:**
   - **Action:** Add tasks to `ansible/roles/control_node/tasks/agents.yml` to download OliveTin (if not installed via Homebrew) and install its launchd agent.

**Verification:** Run `yamllint` on the template to ensure syntax is valid. Run a dry-run playbook check for the control node to ensure template rendering succeeds.
