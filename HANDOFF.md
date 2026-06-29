# upmon — Full Project Handoff

## How to restart this session cheaply

**USE CLAUDE CODE IN THE TERMINAL, NOT WARP.**

Warp's agent burns API credits for every message. Claude Code in the terminal (once you're on Pro) uses your subscription's session limits instead — no per-token billing.

```bash
claude   # opens interactive session in terminal
```

Then paste the contents of this file as your opening message, or say:
> "Read ~/upmon-handoff/HANDOFF.md and resume the upmon project from where we left off."

Make sure `claude --version` shows you're on your Pro subscription account (Danny's account), not an API key. Run `/status` inside Claude Code to confirm plan type shows "Pro" or "Max", not "API".

---

## Device & connectivity facts (verified)

- **Device**: Google Pixel 7a, Android 16, serial `35261JEHN12374` (USB)
- **USB adb**: `adb -s 35261JEHN12374 <cmd>` — most reliable, use this
- **Wireless ADB**: `192.168.68.59:5555` — available only after `adb -s 35261JEHN12374 tcpip 5555` run from Mac over USB. NOT persistent across reboots.
- **SSH to Termux**: ADB port forward required (Android firewall blocks direct WiFi SSH):
  ```bash
  adb -s 35261JEHN12374 forward tcp:8022 tcp:8022
  ssh -i ~/.ssh/termux_key -p 8022 localhost
  ```
- **Tasker**: v6.7.5-beta, package `net.dinglisch.android.taskerm`, `WRITE_SECURE_SETTINGS` granted ✅
- **Shizuku**: `moe.shizuku.privileged.api` installed (stock version)
- **Termux**: `com.termux`, `com.termux.tasker`, `com.termux.boot`, `com.termux.api` all installed ✅
- **maestro CLI**: v2.6.1 at `~/.maestro/bin/maestro` — use `--udid 35261JEHN12374`

## Shell commands verified to work in Android shell (adb shell / Tasker Run Shell)

```bash
# Port check (harmless "Cannot open netlink socket" warning is fine):
ss -tln 2>/dev/null | grep -q ":5555" && echo "PORT_OK" || echo "PORT_CLOSED"

# Shizuku process check:
pgrep -f shizuku > /dev/null 2>&1 && echo "SHIZUKU_OK" || echo "NO_SHIZUKU"
```

---

## FUNDAMENTAL LIMITATION (no root = no persistent port 5555)

**Root cause**: `persist.adb.tcp.port` is the system property that makes port 5555 survive reboots. Setting it requires root:
```
setprop persist.adb.tcp.port 5555   # → "Failed to set property" without root
```

`adb tcpip 5555` only sets the session-scoped `service.adb.tcp.port`, which resets on reboot.
`settings put global adb_wifi_enabled 1` controls Android's new Wireless Debugging UI feature — it has NO effect on port 5555.

**Consequence**: After every cold reboot, you must plug in USB and run:
```bash
adb -s 35261JEHN12374 tcpip 5555
```
This is a one-time step per reboot. Once done, the port stays open until the next reboot.

**What DOES work at boot** (both confirmed via logcat):
- Termux:Boot fires and runs `~/.termux/boot/start-adb.sh`
- Tasker's `ADB_Boot_Restore` Device Boot profile fires and runs `ADB_Core_Watchdog`
- Neither can open port 5555 from within the device — they hit the same wall

**Possible future fixes** (not yet implemented):
1. Rooting the device (would allow `setprop persist.adb.tcp.port 5555`)
2. Android Wireless Debugging (Developer Options → Wireless debugging) — certificate-based, different port per boot, but truly persistent
3. Custom Shizuku fork (thedjchi/shizuku) that may enable `setprop` without full root

---

## Tasker project state on device

- **`upmon` project tab** EXISTS in Tasker ✅
- **`ADB_Core_Watchdog`** task present and active ✅
- **`ADB_Interval_Check`** profile: Time, every 20 min → runs watchdog ✅
- **`ADB_Boot_Restore`** profile: Device Boot event → runs watchdog ✅

### What ADB_Core_Watchdog does (7 actions)

1. **Secure Settings Global** `adb_enabled = 1`
2. **Secure Settings Global** `adb_wifi_enabled = 1` (no-op for port 5555, but harmless)
3. **Run Shell** `adb tcpip 5555` (will fail without USB adb, but try anyway)
4. **Run Shell** port check → `%PORT_CHECK`
5. **Run Shell** Shizuku check → `%SHIZUKU_CHECK`
6. **If** PORT_CLOSED OR NO_SHIZUKU → **Notify** with status details
7. **End If**

---

## Boot sequence (what happens after each reboot)

1. Device boots, user enters PIN (BOOT_COMPLETED delivered only after first unlock)
2. Termux:Boot fires `~/.termux/boot/start-adb.sh`:
   - Starts `sshd` immediately (SSH access available via USB forward after ~5-10s)
   - Waits 30s for WiFi
   - Attempts `adb tcpip 5555` — **will fail, but harmless**
3. Tasker fires `ADB_Boot_Restore` → `ADB_Core_Watchdog`:
   - Enforces `adb_enabled` and `adb_wifi_enabled` settings
   - Attempts `adb tcpip 5555` — **will fail, but harmless**
   - Port check finds PORT_CLOSED → sends notification
4. **Required manual step**: `adb -s 35261JEHN12374 tcpip 5555` from Mac over USB

---

## COMPLETED STEPS (as of 2026-06-29)

### ✅ Step 1 — Tasker project imported and active
- Deleted empty upmon project via maestro (`tasker_import_upmon.yaml`)
- Imported `upmon.prj.xml` via Tasker UI (long-press house → Import Project)
- Both profiles enabled and running ✅

### ✅ Step 2 — Termux SSH configured
- Key: `~/.ssh/termux_key` (ed25519)
- Direct WiFi SSH blocked by Android firewall — use ADB forward instead
- sshd now starts automatically on boot via Termux:Boot ✅

### ✅ Step 3 — Recovery script deployed
- `~/adb_shizuku_watchdog.sh` on device
- Checks port 5555, logs to `~/adb_shizuku_watchdog.log`

### ✅ Step 4 — Termux:Boot persistence configured
- `~/.termux/boot/start-adb.sh` starts sshd, then attempts adb tcpip 5555
- Confirmed firing at boot via logcat ✅

### ✅ Step 5 — Boot persistence tested (2026-06-29)
- Two reboots performed
- Both Termux:Boot and Tasker profiles confirmed firing at boot via logcat
- Port 5555 DOES NOT open autonomously (fundamental limitation documented above)
- Tasker sends notification correctly when port is closed ✅
- sshd DOES start automatically after boot ✅ (added to boot script)

---

## Ongoing monitoring

Tasker checks every 20 minutes. If port 5555 is closed, you get a notification.
Recovery is: plug in USB → `adb -s 35261JEHN12374 tcpip 5555` → done.

---

## REMAINING / NEXT STEPS

### Option A — Accept the limitation (recommended)
The system monitors and notifies correctly. The only gap is port 5555 after cold reboot.
Workflow is: reboot → unlock → plug USB → run one adb command → done.

### Option B — Android Wireless Debugging (no root required)
Developer Options → Wireless debugging → enable. Uses random port per boot, but pairs via certificate. Would require different connection method (not `adb connect IP:5555`).

### Option C — Root the device
Allows `setprop persist.adb.tcp.port 5555` and would make port 5555 fully persistent. Unlocks bootloader required.

---

## Key file paths on Mac

- Handoff dir: `~/upmon-handoff/`
- Tasker XML: `~/upmon-handoff/upmon.prj.xml`
- maestro playbooks: `~/upmon-handoff/.maestro/playbooks/`
- SSH key: `~/.ssh/termux_key`

## Key file paths on Pixel 7a

- Termux home: `/data/data/com.termux/files/home/`
- Boot script: `/data/data/com.termux/files/home/.termux/boot/start-adb.sh`
- Watchdog script: `/data/data/com.termux/files/home/adb_shizuku_watchdog.sh`
- Watchdog log: `/data/data/com.termux/files/home/adb_shizuku_watchdog.log`
- Tasker data: `/sdcard/Tasker/`
