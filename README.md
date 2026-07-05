# stayturgid

Keeps wireless ADB (port 5555) and Shizuku alive on Android across reboots — without root.

## TaskerNet

Import the stayturgid Tasker project directly:

**https://taskernet.com/shares/?user=AS35m8lVOCqN0zylSnJKY8pBzCqkgDU8h624gr9CWqSAxD9myEt6n3OjyI4TtJhMtMw%2B&id=Project%3Astayturgid**

Or follow the manual install steps below.

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
| Tailscale | `com.tailscale.ipn` | Optional but recommended — stable device IP for `adb connect`/SSH (see HACKING.md §1.2) |
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

## Mac-side keepalive

The device-side setup keeps port 5555 open across reboots, but `adb connect` on the Mac side drops when the Mac sleeps or the network flaps. A launchd agent reconnects it automatically every 60 seconds.

The script takes optional args — `adb-reconnect.sh [serial] [lan_ip:port] [tailscale_ip:port]` — and tries the cached address, then the USB-discovered LAN IP, then the Tailscale IP. With no args it defaults to the Pixel 7a. One plist per device:

```bash
# Make the script executable
chmod +x ~/stayturgid/mac/adb-reconnect.sh

# Install and start the launchd agents (7a default + S24 with Tailscale fallback)
cp ~/stayturgid/mac/com.djbclark.stayturgid.adb-reconnect.plist ~/Library/LaunchAgents/
cp ~/stayturgid/mac/com.djbclark.stayturgid.adb-reconnect-s24.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect.plist
launchctl load ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect-s24.plist
```

Verify it loaded:

```bash
launchctl list | grep stayturgid
# Expected: a line with com.djbclark.stayturgid.adb-reconnect (exit code 0)
```

Reconnect events are logged to `~/Library/Logs/stayturgid-adb-reconnect.log`. The script exits silently when the device is already connected, so the log is quiet during normal operation.

### Dead-man's switch

`mac/access-monitor.sh` (via `com.djbclark.stayturgid.access-monitor.plist`, every 5 min) is the alarm that fires when a device is unreachable on **every** path — all ADB addresses *and* an SSH port-8022 probe. It only notifies after ~10 minutes of total outage (so a brief network blip stays quiet) and notifies once again on recovery. This is the "something is actually wrong" signal, distinct from the reconnect agent which silently self-heals transient drops.

```bash
cp ~/stayturgid/mac/com.djbclark.stayturgid.access-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.djbclark.stayturgid.access-monitor.plist
```

Edit the `DEVICES` array in `access-monitor.sh` to match your devices' LAN/Tailscale addresses.

To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect.plist
```

> **Note:** The plist hardcodes `/Users/djbclark/stayturgid/mac/adb-reconnect.sh`. Edit it if you cloned the repo elsewhere.

## SSH access to Termux

Direct WiFi SSH is blocked by Android's firewall. Use ADB port-forward instead:

```bash
adb forward tcp:8022 tcp:8022
ssh -i ~/.ssh/termux_key -p 8022 localhost
```

## Repo structure

```
tasker/
  stayturgid.prj.xml            — Tasker project (import this)
  ADB_Core_Watchdog.tsk.xml     — Task XML (included in project)
  auto-update/
    stayturgid_update_check.tsk.xml — Update-check task (import separately)
    Task_Auto_Update.tsk.xml        — Original upstream task (reference)
    README.md                       — Auto-update integration docs
termux/boot/
  start-adb.sh             — Deploy to ~/.termux/boot/ on device
.maestro/playbooks/        — Maestro automation flows (dev/setup)
```

## Tested on

- Google Pixel 7a, Android 16
- Shizuku thedjchi fork v13.6.0.r1349-thedjchi-beta
- Tasker v6.7.5-beta
