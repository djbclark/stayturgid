# stayturgid

Keeps wireless ADB (port 5555) and Shizuku alive on Android across reboots — without root.

## How it works

After each cold reboot:

1. **Shizuku** ([thedjchi fork](https://github.com/thedjchi/Shizuku)) starts automatically via Android's Wireless Debugging with *TCP mode* enabled — this opens port 5555 without any USB connection.
2. **Termux:Boot** fires `~/.termux/boot/start-adb.sh`, starting `sshd` so the device is reachable via SSH-over-ADB-forward.
3. **Tasker** (`ADB_Boot_Restore` profile) runs `ADB_Core_Watchdog` at boot and every 20 minutes — enforces ADB settings and sends a notification if port 5555 or Shizuku goes down.

## Prerequisites

| App | Package | Notes |
|-----|---------|-------|
| Tasker | `net.dinglisch.android.taskerm` | v6.7.5+, needs `WRITE_SECURE_SETTINGS` |
| Shizuku (thedjchi fork) | `moe.shizuku.privileged.api` | v13.6+ beta — **not** the Play Store version |
| Termux | `com.termux` | Install from F-Droid |
| Termux:Boot | `com.termux.boot` | Install from F-Droid |
| Android | 11+ | Wireless Debugging required |

### Grant Tasker `WRITE_SECURE_SETTINGS`

```bash
adb shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS
```

## Installation

### 1. Shizuku setup

Install the [thedjchi Shizuku fork](https://github.com/thedjchi/Shizuku) APK. In Shizuku → Settings, enable:

- **Start on boot**: ON
- **Watchdog**: ON
- **TCP mode**: ON (port 5555)

Then tap **Start via Wireless debugging → Start** to pair and start Shizuku. Once it's running, subsequent reboots are handled automatically.

### 2. Deploy the Termux boot script

```bash
# From the Mac with device connected via USB:
adb push termux/boot/start-adb.sh /sdcard/start-adb.sh

# Then in Termux on the device:
mkdir -p ~/.termux/boot
cp /sdcard/start-adb.sh ~/.termux/boot/start-adb.sh
chmod +x ~/.termux/boot/start-adb.sh
```

Open the **Termux:Boot** app once to register its `BOOT_COMPLETED` receiver.

### 3. Import the Tasker project

Copy `tasker/stayturgid.prj.xml` to `/sdcard/Tasker/projects/` on the device, then in Tasker long-press the project tab → **Import Project** → select `stayturgid`.

## Verification

After a cold reboot and PIN unlock, wait ~60 seconds, then from the Mac:

```bash
adb shell "ss -tln 2>/dev/null | grep -E ':5555|:8022'"
# Expected: LISTEN lines for both ports

adb connect 192.168.68.xx:5555
# Expected: connected

pgrep -f shizuku && echo SHIZUKU_OK
# Expected: SHIZUKU_OK
```

## SSH access to Termux

Direct WiFi SSH is blocked by Android's firewall. Use ADB port-forward instead:

```bash
adb forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost
```

## Repo structure

```
tasker/
  stayturgid.prj.xml       — Tasker project (import this)
  ADB_Core_Watchdog.tsk.xml — Task XML (included in project)
termux/boot/
  start-adb.sh             — Deploy to ~/.termux/boot/ on device
.maestro/playbooks/        — Maestro automation flows (dev/setup)
```

## Tested on

- Google Pixel 7a, Android 16
- Shizuku thedjchi fork v13.6.0.r1349-thedjchi-beta
- Tasker v6.7.5-beta
