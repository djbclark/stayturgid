# Handoff: Drop Obtainium (Agent 22)

Date: 2026-07-30
Task: Drop Obtainium as a fleet dependency (Issue #119)
Branch: `feature/drop-obtainium`

## Summary of Work

This session removed Obtainium and F-Droid entirely from the `stayturgid` operations suite, per operator direction to rely strictly on immutable `bootstrap_apks` pinned to GitHub releases.

### 1. Codebase Cleanup

- Deleted `ansible_collections/stayturgid/obtainium/` and `ansible_collections/stayturgid/fdroid/`.
- Removed `catalogs/obtainium/` and `control/tools/obtainium/`.
- Removed their invocation from `fleet.yml` and `ensure_apps`.
- Cleared out Obtainium from `bootstrap_apks/defaults/main.yml`.

### 2. Documentation Updates

- Updated `docs/hacking.md` to remove Obtainium, F-Droid, and Shizuku-via-Obtainium instructions.
- Archived `docs/architecture/components/obtainium.md`, `fdroid.md`, and `obtainium-shizuku-handoff.md` to `docs/archive/`.
- Added a 2026-07-30 addendum to `004-self-heal-vs-ansible-coverage.md` officially retiring Obtainium.

### 3. Installer Attribution

- Added `installer: "org.stayturgid.agent"` to the `android_apk` module invocations in `bootstrap_apks/tasks/install_apk.yml`.
- Reordered `bootstrap_apks` so `org.stayturgid.agent` installs first.
- **Safety**: Added a jinja conditional to omit the `installer` param when installing `org.stayturgid.agent` itself, preventing chicken-and-egg validation errors on cold provisioning.

### 4. Upstream Release Checker

- Authored a Python script `control/bin/check_apk_updates.py` leveraging the GitHub API to compare current upstream tags against the pinned `gh_tag` in `bootstrap_apks`.
- Handles both `/releases/latest` and `/tags` to ensure compatibility across repositories.
- Sends a notification to the operator via `hermes -z` when a drift is detected.
- Added a `check-apk-updates` Jobber cron job to `site-djbclark/roles/site_agents/templates/jobber.yaml.j2` to run the checker daily at 10 AM.

## Constraints & Gotchas

- The orchestrator will need to merge this worktree (`feature/drop-obtainium` across both repos) before the next agent proceeds.

✅ Agent 22 completed.
