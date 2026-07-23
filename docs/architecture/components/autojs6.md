# stayturgid AutoJs6 watchdog (retired fleet-wide 2026-07-22, reference only)

**Status: retired.** The K1 native-agent cutover (2026-07-22, commit `195c5c7`)
replaced this watchdog fleet-wide with the Kotlin APK `device/native-agent/`
(OPTIONS **K1**), which now owns inject + co-monitor + shell catastrophic
recovery. The `autojs6_watchdog` Ansible role was retired in the same commit.
**Do not add new fleet-facing AutoJs6 automation** — this code is kept as
reference only. See [docs/STATUS.md](../../STATUS.md) for the current,
**not yet fully verified**, cutover state (AutoJs6 uninstall on some devices
is unconfirmed) and
[handoff-2026-07-23-native-agent-k1.md](../../operations/sessions/handoff-2026-07-23-native-agent-k1.md)
for what remains.

The rest of this document describes the retired runtime as it worked while
live, kept for historical/debugging reference (e.g. the Rhino-engine gotchas
below still apply to anything still executing under `device/autojs6/`).

Secondary layer (historical): notifications, Tailscale probe, catastrophic
Shizuku repair, and a **JS co-monitor** that re-probed the same health surface
as Termux repair on every host every cycle (fleet parity — not Fire-only).

**Routine repair was Termux-primary** (`stayturgid-repair` every 5 min) —
AutoJs6 deferred `RUN_COMMAND` invoke unless the repair log was stale.

Status + remaining steps (historical):
[native-agent-status-2026-07-22.md](../../archive/plans/native-agent-status-2026-07-22.md).
Plan: [autojs6-to-native-apk-plan.md](../../archive/plans/autojs6-to-native-apk-plan.md).

## What it does

| Interval         | Action                                                                                                     |
| ---------------- | ---------------------------------------------------------------------------------------------------------- |
| 20 min + boot    | `main.js` cycle when engine alive                                                                          |
| On catastrophic  | Shizuku `shizuku()` shell repair, then a11y Shizuku Start tap                                              |
| Real-time repair | Only when Termux boot loop stale (>15 min)                                                                 |
| Co-monitor       | `lib/comonitor.js` — sshd / shizuku / a11y / shell5555 / wifi via `shizuku()` **every cycle on all hosts** |

Does **not** replace: Termux:Boot self-heal, Shizuku, Mac `adb_reconnect.py`, Obtainium APK updates.

## Co-monitor (redundancy)

AutoJs6 has Shizuku API shell even when Termux hangs (battery API, Fire
`NO_LOCAL_ADB`, dead boot loop). Each cycle on **oneui-device / stock-android-device / fireos-device**:

1. Termux `[repair]` fresh → still run co-monitor (verify, don't skip)
2. Fire split-storage / Termux stale / bridge-fail → same co-monitor path
3. Co-monitor writes `[comonitor] STATUS port=… shizuku=… sshd=… a11y=…` to
   `/sdcard/stayturgid/logs/watchdog.log`
4. Termux repair dual-writes its STATUS to the same `/sdcard` path so AutoJs6
   can see freshness on Fire

Mac soft-health (`fleet_health_monitor.py`) restarts `main.js` if
`watchdog_stale`/`watchdog_missing` persists (~10 min), so a dead AutoJs6
engine self-heals without a manual `start_watchdog.py`.

## Project path (ASCII only)

Canonical install path (all hosts):

```text
/sdcard/stayturgid/autojs6/main.js
```

Do **not** run or leave a stayturgid project under AutoJs6’s locale sample
directories (`Scripts/` or Chinese **脚本/**). A stale tree at
`/sdcard/脚本/stayturgid` on p7a produced `SyntaxError: Invalid quantifier` when
opening that copy (2026-07-19). Deploy retires those mirrors
(`STALE_PROJECT_MIRRORS` in `autojs6_deploy_util.py`). Policy:
[coding-rules.md — Path and character set](../../coding-rules.md).

## Prerequisites

1. AutoJs6 (`org.autojs.autojs6`) — `setup_autojs6.py` or Obtainium; fleet harden grants storage, `RUN_COMMAND`, notifications, battery unrestricted, unused-app off
2. Termux repair scripts deployed (`deploy_termux.py` / fleet)
3. Shizuku (thedjchi fork), TCP mode
4. **AutoJs6 fleet profile** — `device/autojs6/fleet_profile.json` applied via `FleetProfileActivity` intent by `enable_autojs6_shizuku.py` (no UI automation; uses [operator/AutoJs6 fleet-profile-553](https://github.com/djbclark/AutoJs6) build with [upstream API request](https://github.com/SuperMonster003/AutoJs6/issues/553)).

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

## Rhino JS-engine gotchas — read before touching `device/autojs6/**/*.ts`

`device/autojs6` compiles TypeScript to JavaScript that runs on AutoJs6's
bundled Rhino engine (`RhinoJavaScriptEngine`, `isInterpretedMode = true`),
**not** on Node/V8/QuickJS. tsc and Node-based unit tests both happily
accept code that Rhino cannot actually run — these bugs are invisible until
the compiled output executes on a real device.

The full writeup — four such gotchas found in one session debugging
stayturgid#34, each with a runnable broken-example reproduction and a
verified fix — now lives in the standalone, fork-agnostic
[`autojs6-typescript`](https://github.com/djbclark/autojs6-typescript)
toolkit, vendored here as `vendor/autojs6-typescript/` (git submodule; run
`git submodule update --init` if it's empty). Read
`vendor/autojs6-typescript/docs/RHINO_GOTCHAS.md` before editing anything
under `device/autojs6/**/*.ts`.

This repo consumes that toolkit directly rather than maintaining its own
copy of the checks:

- `tests/test-unit.sh`'s Rhino checks call
  `vendor/autojs6-typescript/tools/check_require_bindings.py` (static: for...of
  syntax + duplicate `require()` binding names) and
  `vendor/autojs6-typescript/tools/rhino_check.py` (a real parse against
  AutoJs6 fork's actual bundled Rhino jar, when one is findable locally)
  against `device/autojs6/main.js` + `device/autojs6/lib/*.js`.
- To update your own local Rhino jar pin or investigate a new gotcha, work
  in the `autojs6-typescript` repo directly and update the submodule
  pointer here (`git -C vendor/autojs6-typescript pull && git add
vendor/autojs6-typescript`) rather than duplicating fixes in both places.

Gotcha #1 (the redeclaration crash) has a confirmed root cause: AutoJs6's
vendored `jvm-npm.js` dropped upstream jvm-npm's per-module Function-wrapper
isolation in favor of delegating to its own installed Rhino
`commonjs.module.Require`, which doesn't isolate `const`/`let` the same way —
entirely an AutoJs6-side change, not an upstream jvm-npm limitation. Reported:
[SuperMonster003/AutoJs6#564](https://github.com/SuperMonster003/AutoJs6/issues/564).
Renaming every shared `require()` binding to a globally-unique name (already
done throughout `device/autojs6/`, enforced by the checks above) is a
workaround, not a fix — it remains necessary until AutoJs6 addresses #564
upstream.
