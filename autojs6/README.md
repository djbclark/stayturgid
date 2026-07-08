# stayturgid AutoJs6 watchdog

Secondary layer: notifications, Tailscale probe, catastrophic Shizuku repair.
**Routine repair is Termux-primary** (`stayturgid-repair` every 5 min) — AutoJs6
defers `RUN_COMMAND` invoke unless the repair log is stale.

## What it does

| Interval | Action |
|----------|--------|
| 20 min + boot | `main.js` cycle when engine alive |
| On catastrophic | Shizuku `shizuku()` shell repair, then a11y Shizuku Start tap |
| Real-time repair | Only when Termux boot loop stale (>15 min) |

Does **not** replace: Termux:Boot self-heal, Shizuku, Mac `adb_reconnect.py`, Obtainium APK updates.

## Prerequisites

1. AutoJs6 (`org.autojs.autojs6`) — `setup_autojs6.py` or Obtainium; fleet harden grants storage, `RUN_COMMAND`, notifications, battery unrestricted, unused-app off
2. Termux repair scripts deployed (`deploy_termux.py` / fleet)
3. Shizuku (thedjchi fork), TCP mode
4. **AutoJs6 drawer fleet profile** — `shared/autojs6_drawer_defaults.json` applied by `enable_autojs6_shizuku.py` (UI automation; upstream API request [AutoJs6 #553](https://github.com/SuperMonster003/AutoJs6/issues/553)).

## Shizuku API (built-in, not a separate plugin)

AutoJs6 ships a global `shizuku(cmd)` function ([docs](https://docs.autojs6.com/#/shizuku)).
`lib/shizuku_shell.js` uses it for privileged shell before falling back to `shell()`.
Catastrophic repair tries `shizuku()` wireless-debug settings before the accessibility
Start-button tap.

Requires: Shizuku running, AutoJs6 authorized in Shizuku, **drawer toggle enabled**.

## Termux bridge

Grant `com.termux.permission.RUN_COMMAND` to AutoJs6 (setup script). Fallback: `repair-bridge.sh` on a 2s poll (`touch run/repair_now`).

## Cycle behavior

1. If repair log fresh → skip routine `invokeRepair` (Termux boot loop owns it)
2. If `CLOSED_NO_SHELL` → `shizuku()` shell attempt, then Shizuku UI tap
3. Tailscale tun0 + coord ping; relaunch on failure
4. Notifications (stable IDs, coalesced)

## Boot / start paths

- **Boot (once):** Termux:Boot → `start-autojs6-watchdog.sh` → `boot-launcher.js` (may use `RunIntentActivity` — acceptable right after unlock)
- **5-min loop:** `stayturgid_autojs6_guard.py` only — logs/notify if main.js stalled; **no** `am start`
- **Mac deploy:** `./start_watchdog.py <host>` or Ansible `autojs6_watchdog` handler

## Layout

```
autojs6/
  main.js, lib/ (watchdog, termux, shizuku, shizuku_shell, tailscale, …)
  scripts/boot-launcher.js
  mac/     — deploy.py, setup_autojs6.py, set_automation_mode.py, enable_autojs6_shizuku.py, start_watchdog.py, grant_shizuku.py, run_test.py
```
