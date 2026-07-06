# Tasker layer — watchdog and auto-update

Tasker project XML for **ADB/Shizuku/sshd monitoring** and optional **GitHub-based project updates**. Use without AutoJs6 (mutually exclusive on one device).

**Full project:** [../README.md](../README.md)

## What this module does

| File | Purpose |
|------|---------|
| `stayturgid.prj.xml` | Main project: `ADB_Core_Watchdog`, update check, daily trigger, boot/interval profiles |
| `ADB_Core_Watchdog.tsk.xml` | Standalone task export (also embedded in project) |
| `auto-update/` | GitHub `version.json` update flow — [auto-update/README.md](auto-update/README.md) |
| `s24_stayturgid.prj.xml` | Historical S24 export (Tasker archived on device; reference only) |

## Standalone use

**Minimum:** Tasker 6.7.5+, AutoInput (for catastrophic Shizuku Start tap and update import dialogs), Termux + Termux:Tasker bridge ([termux/README.md](../termux/README.md)), Shizuku TCP mode.

```bash
# Import project (prefer tasker-io over manual UI):
python3 tasker-io/tasker_io.py <serial> import-task /path/to/wrapped.prj.xml

# Or copy to device and import in Tasker UI — see tasker-io/README.md
```

Grant Tasker:

```bash
adb shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS
```

Deploy Termux bridge:

```bash
# ~/.termux/termux.properties: allow-external-apps=true
# ~/.termux/tasker/stayturgid-repair → execs ~/stayturgid-repair.sh
```

Set automation mode so AutoJs6 does not fight Tasker:

```bash
echo tasker > /sdcard/stayturgid_automation_mode.txt
```

## TaskerNet (optional manual install)

https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtMw%2B&id=Project%3Astayturgid

Auto-update uses **GitHub** [`version.json`](../version.json), not TaskerNet.

## Related docs

- [tasker-io/README.md](../tasker-io/README.md) — reliable task/profile import over ADB
- [auto-update/README.md](auto-update/README.md) — release and update-check workflow
- [autojs6/README.md](../autojs6/README.md) — alternative watchdog (do not run both)
- [termux/README.md](../termux/README.md) — repair script the watchdog calls
