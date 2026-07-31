# ADR 002: Ansible UI tasks vs declarative modules

**Status:** Accepted (2026-07-09). The `android_ui` module this decision
centers on was deleted in #162 (2026-07-31) — its only remaining dispatch
entry (`enable_autojs6_drawer`) was already dead (AutoJs6 retired in K1,
2026-07-22), and `import_obtainium_catalog` had no live caller either. The
architectural reasoning below still applies to any future UI-task module.  
**Supersedes:** nothing (extends [001-ansible-boundary.md](001-ansible-boundary.md))  
**Context:** Operator review — push Ansible integration further without pretending
UI automation is idempotent configuration.

## Decision

1. **Declarative Ansible modules** cover anything provable via adb shell: packages,
   `pm grant`, appops, `settings put`, Shizuku JSON, APK install, fdroidcl/apkeep
   downloads, file push, SSH/Termux state.

2. **UI tasks** cover screen-control flows (Obtainium import, AutoJs6 drawer,
   store first-run when app stores are re-enabled). They are **orchestrated by
   Ansible** but **implemented in shared Python** (`screen_control`, `ui_driver`,
   on-device `stayturgid_*` twins). They are **not** check-mode-idempotent modules
   that claim `changed:` from a single `settings` read.

3. **Runtime self-heal** stays outside Ansible execution (repair loop, AutoJs6
   watchdog, catastrophic Shizuku tap) — unchanged from ADR 001.

## UI task shape (target)

Prefer one of:

| Pattern                                           | When                                                                                                                                                                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`stayturgid.android_common.android_ui` module** | Named `task:` enum (`import_obtainium_catalog`, `enable_autojs6_drawer`, …) with structured args; module calls shared libs; `check_mode: false` or explicit `supported_check_mode: false` |
| **`stayturgid.fleet.post_ui` role**               | Tags per task; tasks call module or thin `command` wrapper; replaces scattered `post-ui.yml` `command` steps                                                                              |

Mac vs on-device routing (SSH-first, fireos-device Mac-adb-only) stays inside the shared
library (`post_ui_remote`), not duplicated in YAML.

**Do not:** one module per tap, per switch, or per OEM layout fragment.

## Module extraction (non-UI, high value)

Move remaining shell-idempotent Mac logic into collections when touched:

| Candidate                | Replaces / complements                                             |
| ------------------------ | ------------------------------------------------------------------ |
| `android_a11y_services`  | `control/bin/a11y_services.py` merge-only backup/restore           |
| `autojs6_project_deploy` | ✅ `autojs6_watchdog` adb path + `deploy.py`                       |
| Expanded validate        | ✅ `stayturgid.fleet.validate` role + thin `validate.yml` playbook |

Retire redundant CLIs when module parity exists (`harden_fleet_apps.py` already
superseded by `android_app_privileges`).

## Package managers

| System            | Declarative (module)                                 | UI task                          |
| ----------------- | ---------------------------------------------------- | -------------------------------- |
| fdroidcl          | `fdroid_repos`, `fdroid_install`, `fdroid_repo_push` | Neo settings (when unparked)     |
| apkeep / gplaycli | `play_apps`, `android_apk`                           | Aurora first-run (when unparked) |
| Obtainium         | `obtainium_app` (catalog render)                     | Import deep link + Continue      |

No Obtainium state API — import remains a UI task until upstream provides one.

## Operator entrypoint

Canonical deploy: `ansible-playbook ansible/playbooks/site.yml` (with
`ANSIBLE_CONFIG=ansible/ansible.cfg`). `deploy_fleet.py` is a thin wrapper for
collection install + `ansible-playbook site.yml`. SSH preflight runs inside
`site.yml` via `preflight.yml` (not in the Python wrapper).

## Consequences

- New UI flows: add a **named UI task** + shared Python implementation; wire in
  `post_ui` role with tags — not a new per-screen module.
- `--check` on site.yml stays honest: UI tasks skipped or no-op with warning.
- Galaxy consumers get clearer split: modules for adb state, documented UI tasks
  for one-time / rare screen work.
- OPTIONS **58–60** shipped (`android_ui`, `post_ui`, `android_a11y_services`,
  `stayturgid.fleet.validate`, `preflight.yml`).

## Non-goals

- Ansible driving 5-min `stayturgid-repair` or AutoJs6 `main.js` intervals
- YAML-stored tap coordinates (stay in code + `device.json`)
- Replacing `make verify` / full TAP with Ansible alone
- 100% elimination of Python — target remains **~80% declarative / ~20% runtime + UI engine**
