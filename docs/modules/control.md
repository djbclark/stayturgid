# Mac-side tools — ADB keepalive and fleet deploy

Python scripts and Ansible-rendered launchd agents for the **Mac control node**.

**Full project:** [../README.md](../README.md)

## What this module does

| File | Purpose |
|------|---------|
| `adb_reconnect.py` | Reconnect `adb connect` when link drops; LAN → Tailscale fallback |
| `access_monitor.py` | Dead-man's switch: notify after ~10 min total outage on all paths |
| `fleet_health_monitor.py` | Soft health scrape (watchdog/a11y/sshd/bootloop) → `fleet-health.log`; restarts stale AutoJs6 `main.js` |
| `fire_help_monitor.py` | Mac→Fire help when Shizuku/Handsets down → `fire-help.log` |
| `fire_peer_help.py` | Peer ADB helper (Handsets/Shizuku) for Fire; SSH ForceCommand entry |
| `check_fleet_health.py` | **Session triage** — agents run at start; exit 1 ⇒ tell operator |
| `gui_audit.py` | Neo/Aurora GUI audit — **parked**; manual only (`docs/modules/fdroid.md`, `docs/modules/play.md`) |
| `verify_play_autoupdate.py` | Play Store auto-update VLM gate (optional; see [docs/vlm.md](../docs/vlm.md)) |
| `vlm_check.py` | Local UI-TARS client smoke test (`make vlm-check`) |
| `deploy_fleet.py` | Full fleet deploy via `site.yml` (preflight → fleet → post-ui → validate) |
| `bootstrap_ssh.py` | First-time Termux SSH: adb + `run-as com.termux` or `--ansible` → `bootstrap.yml` |
| `a11y_services.py` | Backup/restore `enabled_accessibility_services` per host (`control/lib/a11y_profiles.json`) |
| `harden_fleet_apps.py` | Ad-hoc battery/permissions hardening (fleet deploy uses `app_privileges` role) |
| `control/lib/stayturgid_device.py` | Device resolution, Shizuku JSON patch, UI XML parsing |
| `control/lib/fleet_health.py` | Read-only health probes used by `fleet_health_monitor.py` |
| `control/lib/device_screen_lease.py` | Cross-project screen-control lease (DSCL v1) |
| `control/bin/screen_lease.py` | CLI: status/check/acquire/release screen leases |
| Screen-control lease | [docs/modules/screen-control-lease.md](screen-control-lease.md) — interop with other Mac projects |

Launchd agents and `devices.conf` are rendered by `ansible/playbooks/control_node/site.yml`
(`make deploy-mac` or automatically at end of `make deploy`).

## Fleet deploy

```bash
make deploy [HOSTS=s24]                # whole fleet (recommended)
make deploy-check HOSTS=s24            # dry run
./control/bin/bootstrap_ssh.py s24             # first SSH key (when Ansible cannot connect yet)
./control/bin/deploy_fleet.py s24              # same as make deploy
CHECK=1 ./control/bin/deploy_fleet.py s24      # same as make deploy-check
./control/bin/deploy_fleet.py --scope fdroid s24 # F-Droid (parked until app stores re-enabled)
./control/bin/deploy_fleet.py --scope play s24   # Play / Aurora (parked)
```

Verify: `make verify` or `make verify-heal` or `bash tests/run.sh device --heal [host]`

## Standalone ADB keepalive

```bash
# One-shot reconnect (conf-driven alias):
python3 control/bin/adb_reconnect.py s24

# Install launchd agents + Homebrew prereqs from inventory:
make deploy-mac
# or: ansible-playbook ansible/playbooks/control_node/site.yml --tags agents
```

Logs: `~/.config/stayturgid/logs/`. Device list: `~/.config/stayturgid/devices.conf` (from Ansible).

**Launchd agents** (`make deploy-mac` / `ansible/playbooks/control_node/site.yml`):

| Agent | Interval | Log |
|-------|----------|-----|
| `com.stayturgid.adb-reconnect-<host>` | 60 s | `adb-reconnect.log` |
| `com.stayturgid.access-monitor` | 300 s | `access-monitor.log` (reachability) |
| `com.stayturgid.fleet-health` | 300 s | `fleet-health.log` (soft health) |
| `com.stayturgid.fire-help` | 300 s | `fire-help.log` (Fire Shizuku/Handsets) |

`com.stayturgid.gui-audit` is **not** installed while app stores are parked.

**Soft health** (`fleet_health_monitor.py`): when reachable, scrapes watchdog/repair
ages, STATUS `port`/`shizuku`/`a11y`, AutoJs6 + profile a11y drift, boot loop,
`localhost:5555` shell. Always logs; macOS notify after ~10 min debounce.
Disable with `STAYTURGID_SKIP_HEALTH=1`. Does not mutate devices.

**Agents — session start:** `make health` — if exit ≠ 0,
surface host/`issues=` to the operator immediately (see HANDOFF § Mac fleet health).
Any health fix must also update self-heal (Termux / AutoJs6 co-monitor / this
monitor’s `maybe_heal_watchdog`) — see `.cursor/rules/fleet-health-self-heal.mdc`.

UI automation playbook for other agents:
[docs/research/mac-android-ui-automation.md](../docs/research/mac-android-ui-automation.md).

Other subprojects resolve adb targets via [control/lib/stayturgid_device.py](../control/lib/stayturgid_device.py) or [control/lib/resolve_adb.py](../control/lib/resolve_adb.py).

## Related docs

- [README.md § Full stack](../README.md)
- [docs/modules/termux.md](../docs/modules/termux.md) — device-side sshd (SSH probe in access_monitor)
- [control/tools/autojs6/](../control/tools/autojs6/) — AutoJs6 deploy scripts
