# ADR 004: Self-heal vs Ansible deploy coverage — gap analysis

**Status:** Accepted (2026-07-11)  
**Context:** After migrating to djbclark/Shizuku, djbclark/AutoJs6, and djbclark/Obtainium forks with headless APIs, many one-time setup steps were added to the Ansible deploy flow but not to the on-device self-heal loop — and vice versa.

## 1. Coverage matrix

### Present in Ansible deploy (`make deploy` → `fleet/fleet.yml`)

| Capability                                      | In Ansible?                        | In self-heal?                      | Notes                                        |
| ----------------------------------------------- | ---------------------------------- | ---------------------------------- | -------------------------------------------- |
| AutoJs6 fleet profile push + intent             | ✅ `autojs6_watchdog` role         | ❌                                 | Lost if app data cleared                     |
| Shizuku fleet profile (mode=adb, tcp, watchdog) | ✅ `autojs6_watchdog` role         | ❌                                 | Lost if app data cleared                     |
| Shizuku device idle whitelist                   | ✅ `autojs6_watchdog` role         | ❌                                 | Survives reboot; only needed after reinstall |
| HEADLESS_START broadcast                        | ✅ `autojs6_watchdog` role         | ✅ `headlessStart()` in shizuku.js | Intentional redundancy                       |
| USB/WiFi debugging dialog dismissal             | ✅ `enable_autojs6_shizuku.py`     | ❌                                 | One-time per ADB key                         |
| Fleet ADB key authorization                     | ❌ (can't write adb_keys on A11+)  | ❌                                 | Dialog dismissal only viable path            |
| Obtainium catalog import                        | ✅ `import_catalog.py`             | ❌                                 | Deploy-only; no self-heal needed             |
| Shizuku installer toggle for Obtainium          | ✅ `enable_shizuku_installer.py`   | ❌                                 | One-time                                     |
| Termux packages                                 | ✅ `termux_userland` role          | ✅ `pkg upgrade` in boot loop      | OK                                           |
| appops / permissions                            | ✅ `android_common.app_privileges` | ❌ reset on reinstall              | One-time                                     |
| Tailscale always-on VPN                         | ✅ `tailscale_vpn` role            | ✅ JS tailscale probe              | OK                                           |

### Present in self-heal loop (`device/termux/py/stayturgid_repair.py`)

| Capability               | In self-heal?                       | In Ansible?                    | Notes                  |
| ------------------------ | ----------------------------------- | ------------------------------ | ---------------------- |
| sshd restart             | ✅ `sshd_up()` / `sshd_listening()` | ✅ `termux_sshd` module        | Intentional redundancy |
| a11y merge (append-only) | ✅ `_merge_a11y_list()`             | ✅ `enable_autojs6_shizuku.py` | Intentional redundancy |
| Wireless ADB repair      | ✅ `ensure_wireless_debugging()`    | ✅ `tailscale_vpn` role        | Intentional redundancy |
| SSH config restore       | ✅ `ensure_control_et_ssh_config()` | ✅ `termux_userland` role      | OK                     |
| Battery alarm            | ✅ `stayturgid_battery_alarm.py`    | ❌ (not deploy-time)           | Runtime-only, correct  |

### Present in AutoJs6 watchdog (`device/autojs6/lib/`)

| Capability             | In watchdog?                            | In self-heal?           | In Ansible? |
| ---------------------- | --------------------------------------- | ----------------------- | ----------- |
| Shizuku HEADLESS_START | ✅ `headlessStart()`                    | ❌                      | ✅          |
| Shizuku status probe   | ✅ `serverRunning()` / `probeShizuku()` | ✅ `duplicate_branch()` | ❌          |
| a11y check + repair    | ✅ `guard.enforce()` / `comonitor`      | ✅ `_merge_a11l_list()` | ✅          |
| Tailscale health       | ✅ `tailscale.js`                       | ❌                      | ✅          |

## 2. Identified gaps

### Gap A: Fleet profiles not re-applied by self-heal

If AutoJs6 or Shizuku app data is cleared between deploys, the SharedPreferences written by `FleetProfileActivity` are lost. Neither the self-heal loop nor the JS watchdog re-applies them.

**Status:** **Closed 2026-07-11** — `repair_fleet_profiles()` added to `stayturgid_repair.py` step 6. On every 5-min cycle, re-applies both AutoJs6 and Shizuku fleet profiles via `am start` intents, and whitelists Shizuku from device idle. No sentinel file needed — re-applying is fast (~500ms per intent) and idempotent.

### Gap B: Samsung process freezer blocks broadcast receivers

On Samsung devices, the system can freeze the Shizuku Java process even when `shizuku_server` (native daemon) is running. This causes `HEADLESS_STATUS` to return `result=0` (STARTING) even though the daemon is healthy.

**Status:** Mitigated by `pgrep` fallback in all three probe sites.

**Long-term fix:** The Shizuku fork could write daemon status to a file that the shell can read without needing the Java process.

### Gap C: Device idle whitelist not in self-heal

The `dumpsys deviceidle whitelist +moe.shizuku.privileged.api` command runs during deploy but not in the self-heal loop.

**Impact:** Low — the whitelist survives reboots. Only needed after app reinstall.

## 3. Refactoring: Running Ansible on-device?

### Idea

The Termux boot loop could run `ansible-pull` (or `ansible-playbook` with a local checkout) to apply a subset of deploy tasks as part of self-heal. This would eliminate duplication between `stayturgid_repair.py` and the Ansible roles.

### Constraints

- **ansible-core is not in Termux repos.** Installing it requires `pip install ansible-core` (~5 MB) which is feasible but adds weight.
- **Control node secrets.** The playbooks reference `~/.config/stayturgid/adbkey`, `~/.ssh/termux_key`, etc. These would need to be synced to the device or the on-device playbook would need to skip secrets-dependent tasks.
- **Tag granularity.** The relevant self-heal subset is small: fleet profiles, a11y merge, wireless ADB, sshd, Shizuku config. Only ~5 of the ~40 deploy tasks.
- **Git access.** The device would need to clone/pull the repo on every cycle. Unreliable on Fire OS (no Termux loopback).

### Alternative: Shared Python module

A lighter approach: extract the self-heal tasks into a shared Python module under `control/lib/` that both Ansible modules AND `stayturgid_repair.py` import.

For example:

- `control/lib/fleet_profiles.py` — `apply_autojs6_profile()` and `apply_shizuku_profile()` functions
- Called by Ansible `android_intent` tasks at deploy time
- Called by `stayturgid_repair.py` periodically

This avoids duplication at the code level without requiring Ansible on-device.

### Verdict

Running Ansible on-device is architecturally interesting but heavyweight for the gain. The shared-module approach is more practical. **Not recommended for now** — the gap coverage is already adequate with the `pgrep` fallback and the fleet profile deploy-time tasks. If fleet profile drift becomes a real problem, the shared-module approach is the next step.

## 4. The triple-language duplication problem

A deeper issue: the same self-heal logic exists in three languages.

| Operation            | YAML (Ansible)              | Python (repair.py)            | JS (watchdog)              |
| -------------------- | --------------------------- | ----------------------------- | -------------------------- |
| Shizuku status check | ❌                          | `HEADLESS_STATUS` + pgrep     | `HEADLESS_STATUS` + pgrep  |
| HEADLESS_START       | `android_intent` task       | ❌                            | `headlessStart()` function |
| a11y merge           | `enable_autojs6_shizuku.py` | `_merge_a11y_list()`          | `comonitor.mergeA11y()`    |
| Wireless ADB         | `settings put` task         | `ensure_wireless_debugging()` | `tryShellWirelessRepair()` |

Each language was chosen for its context: YAML for Ansible's declarative model, Python for the Mac/device runtime scripts, JS for the in-process AutoJs6 watchdog. But the same recovery primitives end up re-implemented three times with slightly different edge-case handling.

### Why this matters

When a fix is made in one place (e.g., adding `adb_enabled` to `tryShellWirelessRepair()`), it's easy to miss the other two. The 2026-07-11 code review found exactly this class of bug: `tryShellWirelessRepair()` was missing `settings put global adb_enabled 1` while the Python twin had it.

## 5. Concrete proposal: shared `control/lib/fleet_self_heal.py`

Instead of running Ansible on-device or accepting duplication, create a single Python module that Ansible invokes at deploy time AND the self-heal loop calls periodically.

```
control/lib/fleet_self_heal.py
├── apply_autojs6_profile(shell)     # am start FleetProfileActivity
├── apply_shizuku_profile(shell)      # am start FleetProfileActivity
├── whitelist_shizuku(shell)          # dumpsys deviceidle whitelist +
├── ensure_shizuku_running(shell)     # HEADLESS_STATUS → HEADLESS_START → pgrep
├── ensure_wireless_adb(shell)        # settings put global adb_*
└── ensure_autojs6_a11y(shell)        # settings put secure a11y  (merge-only)
```

### Callers

| Caller                                               | How it calls                                                                            | When                |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------- |
| **Ansible** (`android_ui` module or `script` module) | `python3 control/lib/fleet_self_heal.py --host s24 --apply-all`                         | Every `make deploy` |
| **repair.py**                                        | `from control.lib import fleet_self_heal; fleet_self_heal.apply_autojs6_profile(shell)` | Every 5-min cycle   |
| **JS watchdog** (shizuku.js)                         | Keep `headlessStart()` inline — single `am broadcast` is too simple to extract          | 20-min cycle + boot |

### Benefits

- Single source of truth for recovery logic.
- Ansible deploy and self-heal loop agree on what "fixed" means.
- Python can be called from both Ansible (via `script` or `command` module) and Termux shell.
- The JS watchdog keeps only the thin `HEADLESS_START` wrapper (too simple to share).

### Cost

- ~100 lines of Python for the module.
- Existing Ansible `android_intent` tasks would need to change to `script` or `command` module calls — or the module could emit `--dry-run` output for Ansible's change tracking.
- The `repair.py` import path needs `sys.path` setup for `control/lib/` (already done for `stayturgid_shell.py`).

## 6. Refactoring worth it?

With `repair_fleet_profiles()` in `stayturgid_repair.py`, the remaining duplication is:

| Operation           | YAML (Ansible)                 | Python (repair.py)               | JS (watchdog)                 |
| ------------------- | ------------------------------ | -------------------------------- | ----------------------------- |
| Fleet profile apply | `android_intent` task          | ✅ `repair_fleet_profiles()`     | ❌                            |
| Shizuku status      | ❌                             | ✅ `HEADLESS_STATUS` + pgrep     | ✅ `HEADLESS_STATUS` + pgrep  |
| HEADLESS_START      | ✅ `android_intent` (deploy)   | ❌                               | ✅ `headlessStart()`          |
| a11y merge          | ✅ `enable_autojs6_shizuku.py` | ✅ `_merge_a11y_list()`          | ✅ `comonitor.mergeA11y()`    |
| Wireless ADB        | ✅ `settings put` (deploy)     | ✅ `ensure_wireless_debugging()` | ✅ `tryShellWirelessRepair()` |

The remaining duplication is intentional: deploy-time tasks (YAML) configure initial state, while runtime tasks (Python/JS) handle recovery. They overlap on purpose — that's redundancy, not drift.

**Worth refactoring?** No. The shared-module proposal in §5 would eliminate ~5 lines of YAML and ~20 lines of Python, at the cost of a new abstraction layer. The current layout is clearer: Ansible handles deploy-time configuration, the self-heal loop handles runtime recovery, and the JS watchdog handles in-process catastrophic repair. Each has its own scope and failure mode.

**Worth running Ansible on-device?** No. The constraints from §3 still apply (ansible-core dependency, secrets, git access, Fire OS limitations). The `repair_fleet_profiles()` function achieves the same outcome with 10 lines of Python.

## 7. Persistent goal: no deploy/self-heal gaps

Every new capability should answer three questions:

1. **Deploy:** Is it applied by `make deploy`? (Ansible role or task)
2. **Self-heal:** Is it restored by the 5-min repair loop? (`stayturgid_repair.py`)
3. **Catastrophic:** Is it recovered by the 20-min AutoJs6 watchdog? (`watchdog.js` / `comonitor.js`)

At minimum, items 1 and 2 should always be "yes". Item 3 is optional for non-critical settings (e.g., fleet profiles), but mandatory for anything that affects ADB/SSH reachability.

This is now part of the project convention: when adding a fleet-affecting feature, add it to all three tiers, or document in the commit message which tiers are intentionally skipped and why.

To enforce this, the reviewer checklist (`.cursor/rules/` or handoff doc) should include:

> "Does this change affect device behavior? If yes: is it deployed by Ansible, healed by repair.py, and covered by the JS watchdog?"

## 8. Recommendations

1. ✅ **Gap A closed** — `repair_fleet_profiles()` added to self-heal loop.
2. ❌ **Shared module not needed** — remaining duplication is intentional redundancy.
3. ❌ **On-device Ansible not recommended** — constraints outweigh benefits.

## 9. Follow-up research (2026-07-14)

The narrower, additive design in
[Research: adding `ansible-pull` to stayturgid](../research/ansible-pull-architecture-2026-07-14.md)
does not propose replacing the repair loop or running the existing fleet playbook on a
device. It proposes an opt-in S24 pilot for one pull-safe, non-secret local-policy
subset, with push Ansible retained for bootstrap and recovery. ADR 004 remains the
accepted decision until measured pilot results justify a new ADR.
