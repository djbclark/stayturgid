# stayturgid — AutoJs6 watchdog

JavaScript watchdog using [AutoJs6](https://github.com/SuperMonster003/AutoJs6) — the automation stack for stayturgid. Depends on [termux/](../termux/README.md) for repair scripts.

**Full project:** [../README.md](../README.md) · [docs/README.md](../docs/README.md)

## What it does

| Function | Implementation |
|----------|----------------|
| 20 min + boot watchdog | `main.js` + `setInterval`; boot via `boot-launcher.js` / Termux:Boot |
| Real-time repair | Termux `RUN_COMMAND` → `~/stayturgid-repair.sh` |
| Catastrophic Shizuku repair | `lib/shizuku.js` — accessibility tap on **Start** |
| Notifications | `lib/notify.js` — channel `stayturgid` |
| Logging | `/sdcard/stayturgid_watchdog.log` with `(autojs6)` prefix |

Does **not** replace: Termux:Boot self-heal, Shizuku, Mac `adb_reconnect.py`, Obtainium APK updates.

## Prerequisites

1. AutoJs6 (`org.autojs.autojs6`) — `setup_autojs6.py` or Obtainium; grants storage, `RUN_COMMAND`, battery whitelist
2. Termux with `allow-external-apps=true` and repair scripts deployed
3. Shizuku (thedjchi fork), TCP mode
4. AutoJs6 **accessibility service** enabled

## Quick start (Mac)

```bash
./autojs6/mac/setup_autojs6.py s24
./autojs6/mac/set_automation_mode.py s24
./autojs6/mac/start_watchdog.py s24
```

Device resolution uses [shared/mac/stayturgid_device.py](../shared/mac/stayturgid_device.py) via [shared/mac/adb_cli.py](../shared/mac/adb_cli.py).

**Termux bridge:** Grant `com.termux.permission.RUN_COMMAND` to AutoJs6 (setup script). Fallback: `repair-bridge.sh` on a 2s poll.

## Watchdog cycle

1. Stale repair loop check (>15 min)
2. Invoke `stayturgid-repair.sh` via `RUN_COMMAND`
3. Parse latest `[repair] STATUS` from log
4. Notify on bridge failure, sshd down, or Tailscale down
5. If port closed with no shell: Shizuku UI **Start** tap (unlocked screen required)
6. Re-invoke repair after UI path

## Device profiles

`/sdcard/stayturgid_device.json` — rendered by Ansible from the inventory taxonomy (no device names in code); generic defaults apply without it.

## Keeping it alive

- Termux:Boot → `start-autojs6-watchdog.sh` → `boot-launcher.js`
- `start-adb.sh` 5-min loop nudges `boot-launcher.js` only when the watchdog log is stale (>25 min), at most once per 25 min (avoids PiP spam when recovery fails); uses localhost adb shell + force-stop before launch
- Optional: AutoJs6 timed task every 20 min on `main.js`

## Layout

```
autojs6/
  main.js  lib/  devices/  scripts/
  mac/     — deploy.py, setup_autojs6.py, set_automation_mode.py, start_watchdog.py, grant_shizuku.py, run_test.py
```

## Related

- [termux/README.md](../termux/README.md)
- [HANDOFF.md](../HANDOFF.md) — architecture and roadmap
