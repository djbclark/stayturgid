# Handoff 2026-07-27 — Coordinated Release ops-v1.0.5, Systemic ADB Timeouts & Native Agent Stability

## Executive Summary

This session advanced the operations suite through two coordinated release cycles (**`ops-v1.0.4`** and **`ops-v1.0.5`**), landing critical Native Agent Android stability fixes, operational visibility for the local LLM stack, and a systemic timeout guard across all ADB commands to prevent deployment hangs.

All three `~/ops` checkouts (`stayturgid`, `site-djbclark`, `site-private`) are deployed, verified, and live at **`ops-v1.0.5`**.

---

## 1. Fleet & Release State

- **Ops Release Status**:
  ```text
  stayturgid:    ops-v1.0.5 (11235e1)
  site-djbclark: ops-v1.0.5 (0846318)
  site-private:  ops-v1.0.5 (9ba37de)
  ```
- **Fleet Peer Status**:
  - `s24`: Active peer (`0.5.2` verified, `0.6.0` stability fixes landed).
  - `p7a`: Active peer (`0.6.0-boot-stability` online and verified).
  - `hd8`: Authorized target (`v0.5.0` intentional to avoid Fire OS churn; pending #61 cold-boot verification when Shizuku drops naturally).
- **Deployment Invariants**:
  - All development work executed strictly in `~/src/ops-worktrees/` task workspaces.
  - `~/ops` checkouts are deploy-only, clean, and on `master` at tag `ops-v1.0.5`. Zero uncommitted edits or raw pulls in `~/ops`.

---

## 2. Completed Work & Merged Pull Requests

### Native Agent & Android Stability Fixes (stayturgid #77)
- **Tailscale GUI Foregrounding Fix ([#64](https://github.com/djbclark/stayturgid/issues/64))**: Added `isTailscaleTunnelUp()` in `ComonitorProbes.kt` and gated `CatastrophicRepair.kt`'s `am start` on `!isTailscaleTunnelUp()`, suppressing unexpected GUI popups on transient ping timeouts.
- **Shizuku UserService Leak Fix ([#65](https://github.com/djbclark/stayturgid/issues/65))**: Pinned `userServiceArgs.version(1)` in `HostService.kt` to maintain a stable Shizuku key across APK updates. Added `reapStaleUserServices()` in `ShizukuUserService.kt` and `start_agent.py`.
- **Fire OS Reminder Marker Unification ([#66](https://github.com/djbclark/stayturgid/issues/66))**: Standardized `AuthorizeReminder.kt` on internal `filesDir` (app-private) with `run-as` execution across Fire OS and stock Android.

### Local LLM Operational Visibility (site-djbclark #19)
- Added OliveTin user actions for **LiteLLM**, **omlx**, and **Ollama** status and restart (`user_litellm_status`, `user_litellm_restart`, `user_omlx_status`, `user_omlx_restart`, `user_ollama_status`) in `olivetin/user-actions.yaml` ([#12](https://github.com/djbclark/site-djbclark/issues/12)).

### Coordinated Release ops-v1.0.4
- Advanced `ops-release.json` across all three repos to `1.0.4` via version bump PRs (`stayturgid#78`, `site-djbclark#20`, `site-private#9`).
- Published annotated tags and GitHub Releases titled "djbclark ops 1.0.4". Deployed to `~/ops`.

### Systemic ADB Command Timeouts (stayturgid #79)
- **Central Timeout Helper ([#59](https://github.com/djbclark/stayturgid/issues/59))**: Created `adb_timeout.py` in `stayturgid.android_common`. Standardized on two operational tiers:
  - **Fast Queries (30s)**: `adb devices`, `adb connect`, `adb shell getprop`, `pm list`, `settings get`, `adb mdns services`.
  - **Slow Transfers/Installs (180s)**: `adb push`, `adb install`, `gh release download`, `apksigner sign`.
- **Collection Migration**: Migrated `adb_shell.py`, `adb_resolve.py`, `autojs6_deploy_util.py`, `shizuku_grant.py`, `shizuku_start.py`, and `android_apk.py`. Added returncode `124` explicit error reporting.
- **Unit Tests**: Added `test_adb_timeout.py` covering timeout resolution, command prefixing, and double-wrap prevention.

### Coordinated Release ops-v1.0.5
- Advanced `ops-release.json` across all three repos to `1.0.5` via version bump PRs (`stayturgid#80`, `site-djbclark#21`, `site-private#10`).
- Published annotated tags and GitHub Releases titled "djbclark ops 1.0.5". Deployed to `~/ops`.

---

## 3. Quality Gates & Verification

- `stayturgid` `just check`: **PASS (code)** (21/21 ok).
- `stayturgid` `just test`: **PASS** (586 python tests passed, 133 local tests passed, 147 unit tests passed).
- `site-djbclark` `just lint`: **PASS** (19 unittests + `registry_lint.py` OK).
- `just ops-release-status`: **ops-v1.0.5** across all three checkouts.

---

## 4. Open Issues & Recommended Next Steps

1. **Complete Herdr TUI Integration for Goose & Aider ([site-djbclark#12](https://github.com/djbclark/site-djbclark/issues/12))**:
   - Run `goose` and `aider` inside Herdr panes (`h`).
   - Verify process detection via `herdr agent explain --json`.
   - Add keybindings and documentation in `docs/reference/herdr-workstation.md`.
   - File upstream issue on `ogulcancelik/herdr` for official process detection & remote manifests.

2. **Fleet Deploy Speed Optimization ([stayturgid#57](https://github.com/djbclark/stayturgid/issues/57))**:
   - Benchmark `ansible-playbook` execution time across `s24`, `p7a`, and `hd8`.
   - Parallelize independent device plays and streamline serial package upgrade checks.

3. **Cold-Boot STARTED Path Verification ([stayturgid#61](https://github.com/djbclark/stayturgid/issues/61))**:
   - Test cold-boot `STARTED` Shizuku activation path on `hd8` when `hd8` Shizuku naturally drops/restarts.

4. **Functions -> Agent Migration ([stayturgid#62](https://github.com/djbclark/stayturgid/issues/62))**:
   - Migrate remaining bash/python helper functions into `stayturgid-agent` APK.
