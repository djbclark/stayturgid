# Mac-side tools — ADB keepalive and fleet deploy

Python scripts and Ansible-rendered launchd agents for the **Mac control node**.

**Full project:** [../README.md](../README.md)

## What this module does

| File | Purpose |
|------|---------|
| `adb_reconnect.py` | Reconnect `adb connect` when link drops; LAN → Tailscale fallback |
| `access_monitor.py` | Dead-man's switch: notify after ~10 min total outage on all paths |
| `deploy_fleet.py` | Full fleet deploy — Ansible, Obtainium import, app stores, Aurora UI |
| `shared/mac/stayturgid_device.py` | Device resolution, Shizuku JSON patch, UI XML parsing |

Launchd agents are rendered by `ansible/playbooks/mac.yml` (not hand-copied plists).

## Fleet deploy

```bash
./mac/deploy_fleet.py                    # whole fleet
./mac/deploy_fleet.py s24                # one host
CHECK=1 ./mac/deploy_fleet.py s24        # dry run
./mac/deploy_fleet.py --scope fdroid s24 # F-Droid only
./mac/deploy_fleet.py --scope play s24   # Play / Aurora only
```

Verify: `make verify` or `bash tests/run.sh device --heal [host]`

## Standalone ADB keepalive

```bash
# One-shot reconnect (conf-driven alias):
python3 mac/adb_reconnect.py s24

# Install launchd agents from inventory:
ansible-playbook ansible/playbooks/mac.yml
```

Logs: `~/.config/stayturgid/logs/`. Device list: `~/.config/stayturgid/devices.conf` (from Ansible).

Other subprojects resolve adb targets via [shared/mac/stayturgid_device.py](../shared/mac/stayturgid_device.py) or [shared/mac/resolve_adb.py](../shared/mac/resolve_adb.py).

## Related docs

- [README.md § Full stack](../README.md)
- [termux/README.md](../termux/README.md) — device-side sshd (SSH probe in access_monitor)
- [autojs6/mac/](../autojs6/mac/) — AutoJs6 deploy scripts
