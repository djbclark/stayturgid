# stayturgid AutoJs6 watchdog

Secondary layer: notifications, Tailscale probe, catastrophic Shizuku repair,
and a **JS co-monitor** that re-probes the same health surface as Termux repair
on **every host every cycle** (fleet parity — not Fire-only).

**Routine repair is Termux-primary** (`stayturgid-repair` every 5 min) — AutoJs6
defers `RUN_COMMAND` invoke unless the repair log is stale.

## What it does

| Interval | Action |
|----------|--------|
| 20 min + boot | `main.js` cycle when engine alive |
| On catastrophic | Shizuku `shizuku()` shell repair, then a11y Shizuku Start tap |
| Real-time repair | Only when Termux boot loop stale (>15 min) |
| Co-monitor | `lib/comonitor.js` — sshd / shizuku / a11y / shell5555 / wifi via `shizuku()` **every cycle on all hosts** |

Does **not** replace: Termux:Boot self-heal, Shizuku, Mac `adb_reconnect.py`, Obtainium APK updates.

## Co-monitor (redundancy)

AutoJs6 has Shizuku API shell even when Termux hangs (battery API, Fire
`NO_LOCAL_ADB`, dead boot loop). Each cycle on **s24 / p7a / hd8**:

1. Termux `[repair]` fresh → still run co-monitor (verify, don't skip)
2. Fire split-storage / Termux stale / bridge-fail → same co-monitor path
3. Co-monitor writes `[comonitor] STATUS port=… shizuku=… sshd=… a11y=…` to
   `/sdcard/stayturgid/logs/watchdog.log`
4. Termux repair dual-writes its STATUS to the same `/sdcard` path so AutoJs6
   can see freshness on Fire

Mac soft-health (`fleet_health_monitor.py`) restarts `main.js` if
`watchdog_stale`/`watchdog_missing` persists (~10 min), so a dead AutoJs6
engine self-heals without a manual `start_watchdog.py`.

## Prerequisites

1. AutoJs6 (`org.autojs.autojs6`) — `setup_autojs6.py` or Obtainium; fleet harden grants storage, `RUN_COMMAND`, notifications, battery unrestricted, unused-app off
2. Termux repair scripts deployed (`deploy_termux.py` / fleet)
3. Shizuku (thedjchi fork), TCP mode
4. **AutoJs6 fleet profile** — `device/autojs6/fleet_profile.json` applied via `FleetProfileActivity` intent by `enable_autojs6_shizuku.py` (no UI automation; uses [djbclark/AutoJs6 fleet-profile-553](https://github.com/djbclark/AutoJs6) build with [upstream API request](https://github.com/SuperMonster003/AutoJs6/issues/553)).

## Shizuku API (built-in, not a separate plugin)

AutoJs6 ships a global `shizuku(cmd)` function ([docs](https://docs.autojs6.com/#/shizuku)).
`lib/shizuku_shell.js` uses it for privileged shell before falling back to `shell()`.
Catastrophic repair tries `shizuku()` wireless-debug settings before the accessibility
Start-button tap. See [ADR 003](../adr/003-shizuku-catastrophic-recovery.md) for rationale
on why the UI fallback is retained.

Requires: Shizuku running, AutoJs6 authorized in Shizuku, **drawer toggle enabled**.

## Termux bridge

Grant `com.termux.permission.RUN_COMMAND` to AutoJs6 (setup script). Fallback: `bridges.py --mode repair` on a 2s poll (`touch run/repair_now`).

## Cycle behavior

1. If repair log fresh → skip routine `invokeRepair` (Termux boot loop owns it); **still** run co-monitor
2. If `CLOSED_NO_SHELL` → `shizuku()` shell attempt, then Shizuku UI tap
3. Always → `comonitor.run()` (sshd, a11y, shizuku, shell) on every host
4. Tailscale tun0 + coord ping; relaunch on failure
5. Notifications (stable IDs, coalesced)

## Boot / start paths

- **Boot (once):** Termux:Boot → `start-autojs6-watchdog.sh` → `boot-launcher.js` (may use `RunIntentActivity` — acceptable right after unlock)
- **5-min loop:** `stayturgid_autojs6_guard.py` — logs stale watchdog; arms `run/start_autojs6_now` for **autojs6-bridge** (rate-limited); **no** `am start` from the repair loop
- **bridges.py --mode autojs6:** 2s poll of `start_autojs6_now` → `boot-launcher.js` via `am start` (30 min cooldown)
- **Mac deploy / heal:** `./start_watchdog.py <host>` or `fleet_health_monitor` when `watchdog_stale`

## Layout

On device the project lives at `/sdcard/stayturgid/autojs6/` (or `$STAYTURGID_SD/autojs6/` on Fire OS).

```
device/autojs6/
  main.js, lib/ (watchdog, termux, shizuku, shizuku_shell, tailscale, …)
  scripts/boot-launcher.js
control/tools/autojs6/  — deploy.py, setup_autojs6.py, set_automation_mode.py, enable_autojs6_shizuku.py, start_watchdog.py, grant_shizuku.py, run_test.py
```
