# Mac-side tools — ADB keepalive and fleet deploy

Python scripts and Ansible-rendered launchd agents for the **Mac control node**.

**Full project:** [../README.md](../README.md)

## What this module does

| File | Purpose |
|------|---------|
| `adb_reconnect.py` | Reconnect `adb connect` when link drops; LAN → Tailscale fallback |
| `access_monitor.py` | Dead-man's switch (~10 min total outage) + soft health scrape (watchdog/a11y/sshd) into the same log |
| `deploy_fleet.py` | Full fleet deploy via `ansible/playbooks/site.yml` (bootstrap → fleet → post-UI → validate) |
| `bootstrap_ssh.py` | First-time Termux SSH: adb + `run-as com.termux` or `--ansible` → `bootstrap.yml` |
| `a11y_services.py` | Backup/restore `enabled_accessibility_services` per host (`shared/a11y_profiles.json`) |
| `harden_fleet_apps.py` | Ad-hoc battery/permissions hardening (fleet deploy uses `app_privileges` role) |
| `shared/mac/stayturgid_device.py` | Device resolution, Shizuku JSON patch, UI XML parsing |

Launchd agents are rendered by `ansible/playbooks/mac.yml` (not hand-copied plists).

## Fleet deploy

```bash
./mac/bootstrap_ssh.py s24               # first SSH key (when Ansible cannot connect yet)
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

**Soft health (every 5 min when reachable):** `access_monitor.py` scrapes Termux
watchdog/repair ages, last STATUS `a11y=`, and AutoJs6 in the a11y list
(`shared/mac/fleet_health.py`). Always appends `… health via …:` lines to
`access-monitor.log`; macOS notify after ~10 min of the same soft failure
(debounce). Disable with `STAYTURGID_SKIP_HEALTH=1`. Does not mutate devices.

Other subprojects resolve adb targets via [shared/mac/stayturgid_device.py](../shared/mac/stayturgid_device.py) or [shared/mac/resolve_adb.py](../shared/mac/resolve_adb.py).

## Related docs

- [README.md § Full stack](../README.md)
- [termux/README.md](../termux/README.md) — device-side sshd (SSH probe in access_monitor)
- [autojs6/mac/](../autojs6/mac/) — AutoJs6 deploy scripts
