# Mac-side tools — ADB keepalive and outage alerts

Scripts and launchd plists for the **Mac control node**. Fully usable without AutoJs6 or Ansible — you only need `adb` and (optionally) SSH to Termux.

**Full project:** [../README.md](../README.md)

## What this module does

| File | Purpose |
|------|---------|
| `adb-reconnect.sh` | Reconnect `adb connect` when link drops; LAN → Tailscale fallback |
| `com.djbclark.stayturgid.adb-reconnect*.plist` | launchd: run reconnect every 60s (7a default + S24) |
| `access-monitor.sh` | Dead-man's switch: notify after ~10 min total outage on all paths |
| `com.djbclark.stayturgid.access-monitor.plist` | launchd: run monitor every 5 min |
| `deploy-fleet.sh` | Full fleet (`mac/deploy_fleet.py`) |
| `deploy_fleet.py` | Fleet orchestrator — Ansible phases, Obtainium import, Aurora UI |
| `deploy-fdroid.sh` | F-Droid only (`deploy_fleet.py --scope fdroid`) |
| `deploy-play.sh` | Play only (`deploy_fleet.py --scope play`) |
| `fleet-health.sh` | SSH (+ optional ADB) health check for fleet hosts |
| `resolve-adb.sh` | Shim → [shared/mac/resolve-adb.sh](../shared/mac/resolve-adb.sh) |

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

Other subprojects source shared resolve-adb directly:

```bash
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$REPO_ROOT/shared/mac/resolve-adb.sh"
SERIAL="$(resolve_adb s24)"
```

## Related docs

- [README.md § Full stack](../README.md) — Mac keepalive in quick path step 5
- [termux/README.md](../termux/README.md) — device-side sshd (SSH probe in access-monitor)
- [autojs6/mac/](../autojs6/mac/) — deploy scripts that use `shared/mac/resolve-adb.sh`
