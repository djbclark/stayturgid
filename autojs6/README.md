# stayturgid — AutoJs6 watchdog

JavaScript watchdog using [AutoJs6](https://github.com/SuperMonster003/AutoJs6). **Only** automation stack in this repo (Tasker removed 2026-07-06). Depends on [termux/](../termux/README.md) for repair scripts.

**Full project:** [../README.md](../README.md) · [docs/README.md](../docs/README.md)

## What it does

| Function | Implementation |
|----------|----------------|
| 20 min + boot watchdog | `main.js` + `setInterval`; boot via `boot-launcher.js` / Termux:Boot |
| Real-time repair | Termux `RUN_COMMAND` → `~/stayturgid-repair.sh` |
| Catastrophic Shizuku repair | `lib/shizuku.js` — accessibility tap on **Start** |
| Notifications | `lib/notify.js` — channel `stayturgid` |
| Logging | `/sdcard/stayturgid_watchdog.log` with `(autojs6)` prefix |

Does **not** replace: Termux:Boot self-heal, Shizuku, Mac `adb-reconnect.sh`, Obtainium APK updates.

## Prerequisites

1. AutoJs6 (`org.autojs.autojs6`) — `setup-autojs6.sh` or Obtainium
2. Termux with `allow-external-apps=true` and repair scripts deployed
3. Shizuku (thedjchi fork), TCP mode
4. AutoJs6 **accessibility service** enabled

## Quick start (Mac)

```bash
./mac/setup-autojs6.sh p7a p7a    # or s24 s24
./mac/set-automation-mode.sh p7a  # Shizuku grant for AutoJs6
./mac/start-watchdog.sh p7a

# Purge legacy stayturgid Tasker exports (does not uninstall Tasker):
./mac/purge-stayturgid-from-tasker.sh p7a
```

Scripts use [shared/mac/resolve-adb.sh](../shared/mac/resolve-adb.sh) (USB when plugged in, else Tailscale).

**Termux bridge:** Grant `com.termux.permission.RUN_COMMAND` to AutoJs6 (setup script). Fallback: `repair-bridge.sh` on a 2s poll.

## Watchdog cycle

1. Stale repair loop check (>15 min)
2. Invoke `stayturgid-repair.sh` via `RUN_COMMAND`
3. Parse latest `[repair] STATUS` from log
4. Notify on bridge failure, sshd down, or Tailscale down
5. If port closed with no shell: Shizuku UI **Start** tap (unlocked screen required)
6. Re-invoke repair after UI path

## Device profiles

`/sdcard/stayturgid_device.txt` override (`p7a` / `s24`) or auto-detect from model — see `devices/`.

## Keeping it alive

- Termux:Boot → `start-autojs6-watchdog.sh` → `boot-launcher.js`
- `start-adb.sh` 5-min loop also nudges `boot-launcher.js` if deployed
- Optional: AutoJs6 timed task every 20 min on `main.js`

## Layout

```
autojs6/
  main.js  lib/  devices/  scripts/
  mac/     — deploy, setup, start-watchdog, purge-stayturgid-from-tasker
```

## Related

- [termux/README.md](../termux/README.md)
- [HANDOFF.md](../HANDOFF.md) — Tasker removal research
