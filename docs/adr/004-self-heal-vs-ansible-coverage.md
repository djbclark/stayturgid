# ADR 004: Self-heal vs Ansible deploy coverage — gap analysis

**Status:** Draft (2026-07-11)  
**Context:** After migrating to djbclark/Shizuku, djbclark/AutoJs6, and djbclark/Obtainium forks with headless APIs, many one-time setup steps were added to the Ansible deploy flow but not to the on-device self-heal loop — and vice versa.

## 1. Coverage matrix

### Present in Ansible deploy (`make deploy` → `fleet/fleet.yml`)

| Capability | In Ansible? | In self-heal? | Notes |
|---|---|---|---|
| AutoJs6 fleet profile push + intent | ✅ `autojs6_watchdog` role | ❌ | Lost if app data cleared |
| Shizuku fleet profile (mode=adb, tcp, watchdog) | ✅ `autojs6_watchdog` role | ❌ | Lost if app data cleared |
| Shizuku device idle whitelist | ✅ `autojs6_watchdog` role | ❌ | Survives reboot; only needed after reinstall |
| HEADLESS_START broadcast | ✅ `autojs6_watchdog` role | ✅ `headlessStart()` in shizuku.js | Intentional redundancy |
| USB/WiFi debugging dialog dismissal | ✅ `enable_autojs6_shizuku.py` | ❌ | One-time per ADB key |
| Fleet ADB key authorization | ❌ (can't write adb_keys on A11+) | ❌ | Dialog dismissal only viable path |
| Obtainium catalog import | ✅ `import_catalog.py` | ❌ | Deploy-only; no self-heal needed |
| Shizuku installer toggle for Obtainium | ✅ `enable_shizuku_installer.py` | ❌ | One-time |
| Termux packages | ✅ `termux_userland` role | ✅ `pkg upgrade` in boot loop | OK |
| appops / permissions | ✅ `android_common.app_privileges` | ❌ reset on reinstall | One-time |
| Tailscale always-on VPN | ✅ `tailscale_vpn` role | ✅ JS tailscale probe | OK |

### Present in self-heal loop (`device/termux/py/stayturgid_repair.py`)

| Capability | In self-heal? | In Ansible? | Notes |
|---|---|---|---|
| sshd restart | ✅ `sshd_up()` / `sshd_listening()` | ✅ `termux_sshd` module | Intentional redundancy |
| a11y merge (append-only) | ✅ `_merge_a11y_list()` | ✅ `enable_autojs6_shizuku.py` | Intentional redundancy |
| Wireless ADB repair | ✅ `ensure_wireless_debugging()` | ✅ `tailscale_vpn` role | Intentional redundancy |
| SSH config restore | ✅ `ensure_control_et_ssh_config()` | ✅ `termux_userland` role | OK |
| Battery alarm | ✅ `stayturgid_battery_alarm.py` | ❌ (not deploy-time) | Runtime-only, correct |

### Present in AutoJs6 watchdog (`device/autojs6/lib/`)

| Capability | In watchdog? | In self-heal? | In Ansible? |
|---|---|---|---|
| Shizuku HEADLESS_START | ✅ `headlessStart()` | ❌ | ✅ |
| Shizuku status probe | ✅ `serverRunning()` / `probeShizuku()` | ✅ `duplicate_branch()` | ❌ |
| a11y check + repair | ✅ `guard.enforce()` / `comonitor` | ✅ `_merge_a11l_list()` | ✅ |
| Tailscale health | ✅ `tailscale.js` | ❌ | ✅ |

## 2. Identified gaps

### Gap A: Fleet profiles not re-applied by self-heal
If AutoJs6 or Shizuku app data is cleared between deploys, the SharedPreferences written by `FleetProfileActivity` are lost. Neither the self-heal loop nor the JS watchdog re-applies them.

**Impact:** Low (app data cleared is rare). When it happens, the next `make deploy` restores them.

**Fix options:**
1. Add a `repair_fleet_profiles()` call to `stayturgid_repair.py` that checks a sentinel file and re-applies the profiles if missing. (~10 lines)
2. Have the self-heal loop run `enable_autojs6_shizuku.py` periodically. (~1 line)

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

## 4. Recommendations

1. **Short term** — Accept the current gaps. Fleet profile loss requires app data clear + waiting for next deploy, which is rare.
2. **Medium term** — If fleet profile drift becomes observable, add `repair_fleet_profiles()` to `stayturgid_repair.py`.
3. **Not now** — On-device Ansible. The shared-module pattern is a better ROI if duplication grows.
