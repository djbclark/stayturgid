# Mac-side tools — ADB keepalive and outage alerts

Scripts and launchd plists for the **Mac control node**. Fully usable without Tasker, AutoJs6, or Ansible — you only need `adb` and (optionally) SSH to Termux.

**Full project:** [../README.md](../README.md)

## What this module does

| File | Purpose |
|------|---------|
| `adb-reconnect.sh` | Reconnect `adb connect` when link drops; LAN → Tailscale fallback |
| `com.djbclark.stayturgid.adb-reconnect*.plist` | launchd: run reconnect every 60s (7a default + S24) |
| `access-monitor.sh` | Dead-man's switch: notify after ~10 min total outage on all paths |
| `com.djbclark.stayturgid.access-monitor.plist` | launchd: run monitor every 5 min |
| `resolve-adb.sh` | Shared helper: USB serial when plugged in, else Tailscale wireless |

## Standalone use

```bash
chmod +x mac/adb-reconnect.sh mac/access-monitor.sh mac/resolve-adb.sh

# One-shot reconnect (edit serial/IPs in script args or plist):
./mac/adb-reconnect.sh 35261JEHN12374 192.168.68.64:5555 100.65.230.108:5555
./mac/adb-reconnect.sh RFCX219CHKA '' 100.123.218.30:5555

# Install keepalive (edit paths if repo not in ~/stayturgid):
cp mac/com.djbclark.stayturgid.adb-reconnect.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.djbclark.stayturgid.adb-reconnect.plist
```

Edit `access-monitor.sh` `DEVICES` array for your phones. Logs: `~/Library/Logs/stayturgid-adb-reconnect.log`.

Other subprojects source `resolve-adb.sh` for consistent device targeting:

```bash
source mac/resolve-adb.sh
SERIAL="$(resolve_adb s24)"
adb -s "$SERIAL" shell getprop ro.product.model
```

## Related docs

- [README.md § Mac-side keepalive](../README.md)
- [termux/README.md](../termux/README.md) — device-side sshd (SSH probe in access-monitor)
- [autojs6/mac/](../autojs6/mac/) — deploy scripts that use `resolve-adb.sh`
