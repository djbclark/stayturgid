# O-V-G-O Stack Implementation Plan (Agent Instructions)

**Audience:** Junior Developer / Autonomous AI Agent
**Context:** This document provides explicit, step-by-step instructions to implement the hardened O-V-G-O architecture (OpenObserve, VictoriaMetrics, Grafana, OliveTin) outlined in `docs/research/ovgo-stack-architecture.md`.
**End Goal:** Completely replace the legacy custom Python dashboard (`dashboard.py`) and polling monitors (`fleet_health_monitor.py`, `access_monitor.py`) with a modern, resilient, push-based telemetry stack and a clean OliveTin execution interface.

---

## Overall Architecture Overview

1. **Vector (Edge Shipper):** Runs inside the Android Termux environment. Pushes `logcat` and `termux-battery-status` metrics out to the central server instead of relying on Mac-side polling.
2. **VictoriaMetrics & OpenObserve (Central Core):** Single-binary engines running on the Mac control node to receive metrics and logs from the Android devices.
3. **Grafana (Read UI):** Replaces the custom Flask dashboard. Visualizes metrics and logs.
4. **OliveTin (Write UI):** A lightweight Go-based web UI that executes the existing `just` commands (e.g., `just deploy s24`).

## Success Criteria

You will know you have been successful when:

1. The `dashboard.py`, `fleet_health_monitor.py`, and `access_monitor.py` files (and their associated launchd plists in `ansible/roles/control_node/tasks/agents.yml`) are safely removed or disabled.
2. The `termux_userland` Ansible role includes tasks to download and configure the `aarch64-unknown-linux-musl` Vector binary.
3. An OliveTin `config.yaml` is drafted that correctly sources the Mac environment (e.g., Homebrew paths, virtualenvs) and maps to `just` commands.
4. A full `just lint` and `just check` run completes without errors after your changes.

---

## Step-by-Step Execution Plan

### Phase 1: Deprecate Legacy Monitors and Dashboard

_Your goal is to surgically remove the legacy Mac polling scripts and the Flask dashboard._

1. **Remove Python Scripts:**
   - **Target Files:** `control/bin/dashboard.py`, `control/bin/fleet_health_monitor.py`, `control/bin/access_monitor.py`
   - **Action:** Delete these files.
2. **Remove Launchd Plists:**
   - **Target Files:** `ansible/roles/control_node/templates/dashboard.plist.j2`, `ansible/roles/control_node/templates/fleet-health.plist.j2`, `ansible/roles/control_node/templates/access-monitor.plist.j2`
   - **Action:** Delete these files.
3. **Update Ansible Tasks (`ansible/roles/control_node/tasks/agents.yml`):**
   - **Action:** Search for the tasks that render, remove, or unload the plists for `dashboard`, `fleet-health`, and `access-monitor`. Remove these blocks entirely.
   - **Important:** Also remove their corresponding labels from the `_mac_launchd_reload_labels` variable definition at the bottom of the file.
4. **Update `justfile` & `just/fleet.just`:**
   - **Action:** Remove recipes that explicitly call the deleted scripts, such as `just health` and `just errors`.

**Verification:** Run `just check` and `just lint`. Ensure no broken imports or missing file errors occur.

---

### Phase 2: Implement Vector on the Edge (Ansible)

_Your goal is to configure the Android Termux environment to run Vector natively._

1. **Locate the Termux Userland Role:**
   - **Path:** `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml` (or similar file within the `termux_userland` role).
2. **Add Vector Download Task:**
   - **Action:** Add a task using the `ansible.builtin.get_url` (or `unarchive`) module to download the `vector-X.Y.Z-aarch64-unknown-linux-musl.tar.gz` release from GitHub directly into the Termux environment (`/data/data/com.termux/files/usr/bin/vector`).
3. **Configure Vector (`vector.toml`):**
   - **Action:** Create a template `vector.toml.j2` in the role's `templates` directory.
   - **Config Details:** Ensure it defines a `[sources.battery]` exec source (running `termux-battery-status`) and a `[sources.logcat]` file source (tailing `/data/data/com.termux/files/home/logs/logcat.log`). Define sinks pointing to the central Mac IP.
4. **Set up Termux-Services Boot Hook:**
   - **Action:** Add an Ansible task to create a `termux-services` run script for Vector, ensuring it starts automatically on device boot and restarts on failure.

**Verification:** Run `just dryrun-termux` to ensure your new Ansible tasks pass syntax and dry-run checks.

---

### Phase 3: Draft the OliveTin Configuration

_Your goal is to create the operational interface configuration that replaces the `just` CLI usage._

1. **Create the Config File:**
   - **Path:** `control/templates/olivetin-config.yaml`
2. **Define Actions (Buttons):**
   - **Action:** Write YAML defining OliveTin actions. Example targets: "Deploy Fleet", "Verify Drift", "Run Health Checks".
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
           cd {{ .stayturgid_repo_root }} && just --set hosts {{ .host }} deploy
         args:
           - name: host
             type: input
     ```
4. **Deploy OliveTin via Ansible:**
   - **Action:** Add tasks to `ansible/roles/control_node/tasks/agents.yml` to download OliveTin (if not installed via Homebrew) and install its launchd agent.

**Verification:** Run `yamllint control/templates/olivetin-config.yaml` to ensure syntax is valid.

---

## General Rules for Agents

1. **Check Before You Edit:** Always use `view_file` or `grep_search` to understand the current context of a file before modifying it.
2. **Do Not Hallucinate Paths:** All file paths must be exact. Refer to the directory structure using the `list_dir` tool if you are unsure.
3. **Run Verifications Locally:** Use the `just check`, `just lint`, and `just test` commands heavily to catch regressions. If a test fails, you must revert or fix the error before proceeding.
4. **Multi-Agent Protocol:** Before making any edits, run `git fetch origin --prune && git pull --ff-only origin master`. When a phase is complete and passes tests, commit your work with a clear message and push.
