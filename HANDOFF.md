# upmon — Full Project Handoff

## How to restart this session cheaply

**USE CLAUDE CODE IN THE TERMINAL, NOT WARP.**

```bash
claude   # opens interactive session in terminal
```

Run `/status` inside Claude Code to confirm plan type shows "Pro" or "Max", not "API".

---

## PROJECT STATUS: COMPLETE ✅

Port 5555 opens automatically after every cold reboot — no USB required.

### Verified boot sequence (tested 2026-06-29)
1. Device reboots, user enters PIN
2. **Shizuku** (thedjchi fork v13.6) starts automatically via Wireless Debugging
3. Shizuku's **TCP mode** calls `adb tcpip 5555` via the WD connection → port 5555 opens
4. **Termux:Boot** fires `~/.termux/boot/start-adb.sh` → starts sshd
5. **Tasker** `ADB_Boot_Restore` profile fires → runs `ADB_Core_Watchdog`
6. Tasker finds port 5555 open → no alert sent

Confirmed after reboot:
- `ss -tln | grep :5555` → LISTEN ✅
- `ss -tln | grep :8022` → LISTEN ✅
- `pgrep -f shizuku` → SHIZUKU_OK ✅
- `adb connect 192.168.68.59:5555` → connected ✅

---

## Device & connectivity facts (verified)

- **Device**: Google Pixel 7a, Android 16, serial `35261JEHN12374` (USB) / `192.168.68.59:5555` (wireless)
- **Wireless ADB**: `adb connect 192.168.68.59:5555` — persistent across reboots ✅
- **SSH to Termux**:
  ```bash
  adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
  ssh -i ~/.ssh/termux_key -p 8022 localhost
  ```
  (Direct WiFi SSH blocked by Android firewall — use ADB forward)
- **Tasker**: v6.7.5-beta, `net.dinglisch.android.taskerm`, `WRITE_SECURE_SETTINGS` granted ✅
- **Shizuku**: thedjchi fork v13.6.0.r1349, `moe.shizuku.privileged.api` ✅
- **Termux**: `com.termux`, `com.termux.tasker`, `com.termux.boot`, `com.termux.api` ✅
- **maestro CLI**: v2.6.1 at `~/.maestro/bin/maestro`, use `--udid 35261JEHN12374`

---

## What makes it work: Shizuku thedjchi fork settings

In Shizuku → Settings (gear icon):

| Setting | Value |
|---------|-------|
| Start on boot | ON |
| Watchdog (restart if crash) | ON |
| TCP mode | ON |
| TCP port | 5555 (default) |
| Auto-disable USB debugging | OFF |

**TCP mode** is the key: after Shizuku starts via Wireless Debugging on boot, it uses the WD connection to call `adb tcpip 5555`, opening port 5555 without any USB connection.

---

## Tasker project state

- **`upmon` project** active in Tasker ✅
- **`ADB_Core_Watchdog`** task (7 actions) ✅
- **`ADB_Interval_Check`** profile: every 20 min ✅
- **`ADB_Boot_Restore`** profile: Device Boot event ✅

### ADB_Core_Watchdog actions
1. Secure Settings: `adb_enabled = 1`
2. Secure Settings: `adb_wifi_enabled = 1`
3. Run Shell: `adb tcpip 5555` (belt-and-suspenders; Shizuku usually handles this)
4. Run Shell: port check → `%PORT_CHECK`
5. Run Shell: Shizuku check → `%SHIZUKU_CHECK`
6. If PORT_CLOSED OR NO_SHIZUKU → Notify
7. End If

---

## Termux boot script

`~/.termux/boot/start-adb.sh` on device:
```bash
#!/data/data/com.termux/files/usr/bin/bash
sshd
sleep 30
adb connect 127.0.0.1:5555 || true
adb tcpip 5555 || true
```

The `sshd` line ensures SSH-over-ADB-forward works within seconds of unlock.
The adb lines are belt-and-suspenders; Shizuku TCP mode typically beats them to it.

---

## Ongoing monitoring

Tasker checks every 20 minutes. If port 5555 ever closes (e.g., Shizuku crash), the Watchdog notifies and attempts recovery. Shizuku's own Watchdog also auto-restarts it if it crashes.

---

## Key file paths on Mac

- Handoff dir: `~/upmon-handoff/`
- Tasker XML: `~/upmon-handoff/upmon.prj.xml`
- maestro playbooks: `~/upmon-handoff/.maestro/playbooks/`
- SSH key: `~/.ssh/termux_key`

## Key file paths on Pixel 7a

- Boot script: `~/.termux/boot/start-adb.sh` (Termux home)
- Watchdog script: `~/adb_shizuku_watchdog.sh`
- Watchdog log: `~/adb_shizuku_watchdog.log`
- Tasker data: `/sdcard/Tasker/`
