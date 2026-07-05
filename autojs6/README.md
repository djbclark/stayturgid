# stayturgid — AutoJs6 alternative stack

Parallel implementation of the **Tasker + AutoInput watchdog layer** using [AutoJs6](https://github.com/SuperMonster003/AutoJs6). Run **either** this stack **or** the Tasker stack — never both. The Termux layer (`start-adb.sh`, `stayturgid-repair.sh`) is shared and unchanged.

## What this replaces

| Tasker + AutoInput | AutoJs6 |
|--------------------|---------|
| `ADB_Core_Watchdog` (20 min + boot) | `main.js` + 20 min `setInterval` |
| Termux:Tasker → `stayturgid-repair` | Termux `RUN_COMMAND` intent → same script |
| AutoInput gesture → Shizuku "Start" | Accessibility text/coord tap in `lib/shizuku.js` |
| Tasker notifications | `lib/notify.js` (Android notification channel `stayturgid`) |
| Shared log `/sdcard/stayturgid_watchdog.log` | Same log file, `[watchdog] … (autojs6)` prefix |

## What this does **not** replace

- Termux:Boot self-heal loop (`termux/boot/start-adb.sh`)
- `stayturgid-repair.sh` (shell repairs via localhost:5555)
- Shizuku TCP mode, Mac `adb-reconnect.sh`, `access-monitor.sh`
- Tasker auto-update flow (still Tasker+AutoInput only for now)

## Prerequisites

1. **AutoJs6** installed (`org.autojs.autojs6`) — GitHub release or **Obtainium** (`obtainium/mac/sync-to-device.sh p7a autojs6`)
2. **Termux** with `allow-external-apps=true` and `~/stayturgid-repair.sh` deployed (same as Tasker path)
3. **Shizuku** (thedjchi fork) paired and working
4. AutoJs6 **accessibility service** enabled
5. Tasker + AutoInput accessibility **disabled** when using this stack

## Quick start

### From Mac

```bash
# Full install + deploy + repair-bridge (leaves Tasker mode unchanged)
./mac/setup-autojs6.sh s24 s24          # USB preferred when plugged in; or p7a p7a

# Or deploy only (AutoJs6 already installed):
./mac/deploy.sh s24 s24

# Switch mode when ready to test AutoJs6 stack:
./mac/set-automation-mode.sh s24 autojs6

# Launch watchdog (after mode switch + a11y enabled):
./mac/start-watchdog.sh s24 s24
```

**ADB target:** Mac scripts source `mac/resolve-adb.sh` — `s24`/`p7a` aliases use USB serial when the phone is plugged in, else Tailscale wireless.

**Shizuku authorized apps:** The manager UI reads `/data/local/tmp/shizuku/shizuku.json`, not just `pm grant`. When switching modes, run `./mac/grant-shizuku.sh s24 autojs6` (or use `set-automation-mode.sh`, which calls it automatically) to allow AutoJs6 and deny Tasker.

**Termux bridge:** AutoJs6 v6.4.1+ declares `com.termux.permission.RUN_COMMAND`; grant via setup script or Settings → AutoJs6 → Additional permissions. Fallback: `termux/repair-bridge.sh` (2s trigger file poll) — started automatically by `setup-autojs6.sh` over SSH. The bridge trigger is **always armed** alongside RUN_COMMAND (RUN_COMMAND can start without executing if Termux is cold).

**Rhino note:** AutoJs6 uses Mozilla Rhino — do not use `(?i)` inline regex flags; use `/pattern/i` instead.

### On device (mode switch without Mac)

In AutoJs6, run `scripts/switch-to-autojs6.js` or `scripts/switch-to-tasker.js`, then follow the toast instructions.

## Mutual exclusivity guard

`lib/guard.js` enforces:

1. `/sdcard/stayturgid_automation_mode.txt` must contain `autojs6` (default if missing: `tasker` → script exits)
2. Tasker + AutoInput accessibility services must **not** be enabled
3. AutoJs6 accessibility must be enabled

No cross-fallback: if mode is `tasker`, this script refuses to start even if left on disk.

## Watchdog cycle (per run)

Mirrors `ADB_Core_Watchdog` v3:

1. Check repair loop stale (>15 min since last `[repair]` line) **before** invoke
2. Invoke `stayturgid-repair.sh` via Termux `RUN_COMMAND` (real-time, not stale log)
3. Parse latest `[repair] STATUS` from `/sdcard/stayturgid_watchdog.log`
4. Notify if bridge failed, sshd down, or Tailscale down (`tun0` + ping `100.100.100.100`)
5. If `port=CLOSED_NO_SHELL`: notify → launch Shizuku → tap **Start** (text match, coord fallback)
6. Re-invoke repair after catastrophic UI path

**Caveat:** UI repair requires an **unlocked screen** (same as AutoInput path). Screen-off skips the Shizuku tap.

## Device profiles

Auto-detected from `device.model`, overridable via `/sdcard/stayturgid_device.txt` (`p7a` or `s24`):

- `devices/p7a.js` — Pixel 7a coords + Tailscale IP
- `devices/s24.js` — S24 coords + Samsung wireless-debug UI fallback

## Device path (ASCII only)

Deploy target is always **`/sdcard/Scripts/stayturgid`** — no locale-specific or non-ASCII path mirrors.

## Keeping it alive (no AutoJs6 timed-task UI required)

1. **`main.js`** — internal 20-minute `setInterval` + `timers.keepAlive()` when available.
2. **`termux/boot/start-autojs6-watchdog.sh`** — on boot (mode=autojs6), launches `scripts/boot-launcher.js` after ~45s.
3. **`termux/boot/start-adb.sh` loop** — every 5 minutes, re-invokes `boot-launcher.js` if mode=autojs6 (no-op when `main.js` already running).

Optional: add AutoJs6 **Timed task** entries in the app UI as an extra backup if Doze kills the script process.

Recommended AutoJs6 app settings:

- Enable **stable mode** / ignore battery optimization for AutoJs6

## Validation checklist

After switching to AutoJs6 mode on a test device:

```bash
# Watch shared log
adb shell tail -f /sdcard/stayturgid_watchdog.log
# Expect: [watchdog] … (autojs6) lines every 20 min

# Healthy cycle
# [watchdog] port=open sshd=up … (autojs6)

# Catastrophic test (advanced): pause Termux boot loop, inject CLOSED_NO_SHELL, run cycle manually
# Or validate UI tap only (S24-friendly — does not break 5555):
adb shell am start -a android.intent.action.VIEW \
  -d "file:///sdcard/Scripts/stayturgid/scripts/test-catastrophic-once.js" \
  -t "text/javascript" \
  -n org.autojs.autojs6/org.autojs.autojs.external.open.RunIntentActivity
# Expect: [watchdog] shizuku Start tapped (text match) … ok=true

# Tailscale probe (healthy path)
# …/scripts/test-tailscale-probe-once.js
# Expect: tailscale-probe-test tun=true ping=true up=true

# Stale loop (synthetic 20-min-old [repair] line — no 15-min wait)
# …/scripts/test-stale-loop-once.js
# Expect: isStaleBefore=true + "Repair loop stale" notification

# Locked screen catastrophic (lock first via adb shell input keyevent 26)
# …/scripts/test-locked-screen-catastrophic-once.js
# Expect: shizuku Start skipped — screen off … ok=false
```

**Obtainium quieter installs:** `./obtainium/mac/enable-shizuku-installer.sh s24` (unlocked screen).

## File layout

```
autojs6/
  main.js                 — entry point
  project.json            — AutoJs6 project metadata
  lib/
    config.js             — paths, intervals, a11y service IDs
    guard.js              — mutual exclusivity
    log.js                — shared watchdog log
    notify.js             — Android notifications
    termux.js             — RUN_COMMAND bridge
    shizuku.js            — catastrophic UI repair
    tailscale.js          — tun0 + coord ping probe, relaunch
    repair.js             — repair orchestration
    watchdog.js           — one cycle logic
  devices/p7a.js, s24.js
  scripts/switch-to-*.js, test-*-once.js
  mac/deploy.sh, set-automation-mode.sh, grant-shizuku.sh
  COMPARISON.md           — Tasker vs AutoJs6 evaluation framework
```

## See also

- `COMPARISON.md` — structured pros/cons template (fill in after live testing)
- `../HANDOFF.md` — fleet status and roadmap
- `../termux/stayturgid-repair.sh` — shared repair script
