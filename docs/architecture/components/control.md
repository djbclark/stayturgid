# Mac-side tools — ADB keepalive and fleet deploy

Python scripts and Ansible-rendered launchd agents for the **Mac control node**.

**Full project:** [../../README.md](../../README.md)

## What this module does

| File                                                     | Purpose                                                                                                                           |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `adb_reconnect.py`                                       | Reconnect `adb connect` when link drops; LAN → Tailscale fallback                                                                 |
| `access_monitor.py`                                      | Dead-man's switch: notify after ~10 min total outage on all paths                                                                 |
| `fleet_health_monitor.py`                                | Soft health scrape (watchdog/a11y/sshd/bootloop) → `fleet-health.log`; restarts stale AutoJs6 `main.js`                           |
| `fire_help_monitor.py`                                   | Mac→Fire: resolve_adb (mDNS wireless-debug), keep `adb_wifi_enabled`, Shizuku/Handsets → `fire-help.log`                          |
| `fire_peer_help.py`                                      | Peer ADB helper (Handsets/Shizuku) for Fire; SSH ForceCommand entry                                                               |
| `check_fleet_health.py`                                  | **Session triage** — agents run at start; exit 1 ⇒ tell operator                                                                  |
| `dashboard.py`                                           | Flask + HTMX fleet dashboard; human-action cards include the H8 Shizuku open/test action                                          |
| `check_et_mac.py` / `ensure_et_mac.py`                   | Phone→Mac ET authorized_keys + health/probe                                                                                       |
| `gui_audit.py`                                           | Neo/Aurora GUI audit — **parked**; manual only (`docs/architecture/components/fdroid.md`, `docs/architecture/components/play.md`) |
| `verify_play_autoupdate.py`                              | Play Store auto-update VLM gate (optional; see [docs/architecture/vlm.md](../vlm.md))                                             |
| `verify_hd8_google.py` / `fix_hd8_google_stack.py`       | Fire HD Play/GMS stack verify + optional reinstall                                                                                |
| `vlm_check.py`                                           | Local UI-TARS client smoke test (`just vlm-check`)                                                                                |
| `vlm_upstream_check.py`                                  | Weekly RQS VLM.md best-practice sync check                                                                                        |
| `deploy_fleet.py`                                        | Full fleet deploy via `site.yml` + **always** re-runs `control_node` (device `--limit` skips localhost)                           |
| `deploy_termux.py`                                       | Termux-only deploy wrapper                                                                                                        |
| `bootstrap_ssh.py`                                       | First-time Termux SSH: adb + `run-as com.termux` or `--ansible` → `bootstrap.yml`                                                 |
| `a11y_services.py`                                       | Backup/restore `enabled_accessibility_services` per host (`control/lib/a11y_profiles.json`)                                       |
| `harden_fleet_apps.py`                                   | Ad-hoc battery/permissions hardening (fleet deploy uses `app_privileges` role)                                                    |
| `termux_pkg_nightly.py`                                  | Nightly `pkg update/upgrade` orchestrator (launchd)                                                                               |
| `h2_confirm_ui.py`                                       | One-off UI confirm helpers                                                                                                        |
| `screen_lease.py`                                        | CLI: status/check/acquire/release screen leases (DSCL v1)                                                                         |
| `control/lib/stayturgid_device.py`                       | Device resolution, `devices.conf` parse, Shizuku JSON, UI XML                                                                     |
| `control/lib/fleet_health.py`                            | Read-only health probes used by `fleet_health_monitor.py`                                                                         |
| `control/lib/device_screen_lease.py`                     | Cross-project screen-control lease (DSCL v1)                                                                                      |
| `control/lib/et_mac.py` / `vlm_gate.py` / `vlm_cloud.py` | ET Mac helpers; local + cloud VLM gates                                                                                           |
| Screen-control lease                                     | [docs/architecture/components/screen-control-lease.md](screen-control-lease.md) — interop with other Mac projects                 |

Launchd agents and `devices.conf` are rendered by `ansible/playbooks/control_node/site.yml`
(`just deploy-mac` or automatically at end of `just deploy`).

## Fleet deploy

```bash
# just --set hosts s24 deploy                # whole fleet (recommended)
# just --set hosts s24 deploy-check          # dry run
./control/bin/bootstrap_ssh.py s24             # first SSH key (when Ansible cannot connect yet)
./control/bin/deploy_fleet.py s24              # same as just deploy
CHECK=1 ./control/bin/deploy_fleet.py s24      # same as just deploy-check
./control/bin/deploy_fleet.py --scope fdroid s24 # F-Droid (parked until app stores re-enabled)
./control/bin/deploy_fleet.py --scope play s24   # Play / Aurora (parked)
```

Verify: `just verify` or `just verify-heal` or `bash tests/run.sh device --heal [host]`

### Dashboard Shizuku authorization (H8)

The dashboard runs on `127.0.0.1:4097` (normally published through the control-node
proxy). When a device reports `shizuku_down`, its card offers **open Shizuku and
test rish**. The action opens the Shizuku app through the device shell, then runs
the canonical Termux probe over SSH:

```bash
~/.stayturgid/bin/rish -c 'id -u'
```

Only output `2000` counts as success. Android authorization remains human-gated;
select **Allow all the time** on the phone when prompted, then press the dashboard
button again. A missing Termux SSH path (for example HD8) is reported rather than
silently falling back to a misleading success state.

## Standalone ADB keepalive

```bash
# One-shot reconnect (conf-driven alias):
python3 control/bin/adb_reconnect.py s24

# Install launchd agents + Homebrew prereqs from inventory:
just deploy-mac
# or: ansible-playbook ansible/playbooks/control_node/site.yml --tags agents

# One-time optional system PATH setup (one sudo authentication).
just system-homebrew-path-setup

# Later runs only inspect and report drift; they do not invoke sudo.
just system-homebrew-path-status
```

Logs: `~/.config/stayturgid/logs/`. Device list: `~/.config/stayturgid/devices.conf` (from Ansible).

**Launchd agents** (`just deploy-mac` / `ansible/playbooks/control_node/site.yml`):

| Agent                                 | Interval         | Log                                                          |
| ------------------------------------- | ---------------- | ------------------------------------------------------------ |
| `com.stayturgid.adb-reconnect-<host>` | 60 s             | `adb-reconnect.log`                                          |
| `com.stayturgid.access-monitor`       | 300 s            | `access-monitor.log` (reachability)                          |
| `com.stayturgid.fleet-health`         | 300 s            | `fleet-health.log` (soft health)                             |
| `com.stayturgid.fire-help`            | 300 s            | `fire-help.log` (Fire Shizuku/Handsets)                      |
| `com.stayturgid.termux-pkg-nightly`   | daily 04:15      | `termux-pkg-nightly.log` (`pkg update`/`upgrade` all hosts)  |
| `com.stayturgid.vlm-upstream-check`   | weekly Sun 09:20 | Compare `~/src/RevengeQuickSwitcher/VLM.md` best practices   |
| `com.stayturgid.hermes-gateway`       | KeepAlive        | Hermes Agent Telegram gateway → `~/.hermes/logs/gateway.log` |

`com.stayturgid.gui-audit` is **not** installed while app stores are parked.

### Hermes Agent + Telegram (control node)

[Hermes Agent](https://hermes-agent.nousresearch.com/) is installed via Homebrew (`hermes-agent`)
and kept up by `just deploy-mac` / `control_node` agents:

| Path                                                         | Purpose                                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `ansible/roles/control_node/tasks/hermes.yml`                | Install, model config, `.env` allowlist, launchd plist                          |
| `~/.hermes/config.yaml`                                      | Default model (e.g. `grok-4.5`)                                                 |
| `~/.hermes/.env`                                             | **Secrets** — `TELEGRAM_BOT_TOKEN`, optional allowlist (mode `0600`, never git) |
| `~/.hermes/auth.json`                                        | xAI OAuth tokens after `hermes auth add xai-oauth`                              |
| `~/Library/LaunchAgents/com.stayturgid.hermes-gateway.plist` | KeepAlive gateway                                                               |

**First-time (human):**

```bash
# SuperGrok / Premium+ OAuth (browser)
hermes auth add xai-oauth --type oauth

# Bot token from @BotFather → ~/.hermes/.env
# TELEGRAM_BOT_TOKEN=123:AA…

just deploy-mac
# or: ansible-playbook ansible/playbooks/control_node/site.yml --tags hermes,agents-ensure
```

Site allowlist (Telegram numeric user ids) lives in `ansible/inventory/hosts.yml`
(`stayturgid_hermes_telegram_allowed_users`). Pairing: `hermes pairing approve telegram CODE`.

Disable: `-e stayturgid_hermes_enabled=false` or `stayturgid_hermes_gateway_enabled=false`.

**Soft health** (`fleet_health_monitor.py`): when reachable, scrapes watchdog/repair
ages, STATUS `port`/`shizuku`/`a11y`, AutoJs6 + profile a11y drift, boot loop,
`localhost:5555` shell. Always logs; macOS notify after ~10 min debounce.
Also rate-limits `ensure_et_mac.py` (phone→Mac fleet keys). Disable with
`STAYTURGID_SKIP_HEALTH=1` or `STAYTURGID_SKIP_ET_MAC=1`. Does not mutate devices
except ET authorized_keys reconcile + existing watchdog/Google heals.

### Phone → Mac Eternal Terminal

Phones use **Eternal Terminal** (`et`) to the Mac control node’s `etserver`
(Homebrew LaunchDaemon `homebrew.mxcl.et`, port **2022**). The client always
**bootstraps over SSH** first — TCP 2022 alone is not enough.

| Piece                | Where                                                                         | What                                                                |
| -------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Fleet pubkeys on Mac | `~/.ssh/authorized_keys` marked `# BEGIN/END STAYTURGID-ET-MAC`               | Unrestricted `id_ed25519_fleet` from each host                      |
| Peer-help keys       | Same file, **outside** the block                                              | ForceCommand `fire_peer_help.py` — never overwritten by ET ensure   |
| Device SSH config    | Termux `~/.ssh/config` markers `STAYTURGID-CONTROL-ET`                        | `Host mac …` → Tailscale IP, `IdentityFile ~/.ssh/id_ed25519_fleet` |
| Self-heal Mac        | `control/bin/ensure_et_mac.py` via `just deploy-mac` / fleet-health           | Re-collects pubs + rewrites marked block                            |
| Self-heal device     | `stayturgid_repair` + share file                                              | Restores config from `~/.stayturgid/share/ssh-config-control-et`    |
| Inventory            | `stayturgid_control_*` / `stayturgid_mac_peer` in `group_vars/stayturgid.yml` | User, Tailscale IP, LAN IP, et port                                 |

```bash
# Control node (idempotent)
python3 control/bin/ensure_et_mac.py
python3 control/bin/check_et_mac.py
python3 control/bin/check_et_mac.py --probe-host s24

# From Termux (after deploy-termux)
et mac
et -c 'hostname; whoami' mac
ssh -o BatchMode=yes mac true
```

**Passphrase policy:** phone→Mac must use a **non-passphrase** key
(`id_ed25519_fleet`). Passphrase-protected `id_ed25519` breaks BatchMode/et.
Do **not** use `et --macserver` on Apple Silicon Homebrew (wrong
`/usr/local/bin/etterminal` path); Mac `~/.zshenv` Homebrew PATH is enough.

**Host keys (default Tailscale-friendly):** fleet SSH uses
`StrictHostKeyChecking=accept-new`. To pin known hosts:
`STAYTURGID_SSH_STRICT_HOST_KEY=yes` and
`STAYTURGID_SSH_KNOWN_HOSTS=~/.ssh/known_hosts_stayturgid` (see `control/lib/et_mac.py`).

**Agents — session start:** `just health` — if exit ≠ 0,
surface host/`issues=` to the operator immediately (see HANDOFF § Mac fleet health).
Any health fix must also update self-heal (Termux / AutoJs6 co-monitor / this
monitor’s `maybe_heal_watchdog`) — see `.cursor/rules/fleet-health-self-heal.mdc`.

UI automation playbook for other agents:
[docs/research/mac-android-ui-automation.md](../../research/mac-android-ui-automation.md).

Other subprojects resolve adb targets via [control/lib/stayturgid_device.py](../../../control/lib/stayturgid_device.py) or [control/lib/resolve_adb.py](../../../control/lib/resolve_adb.py).

## Related docs

- [README.md § Full stack](../../README.md)
- [docs/architecture/components/termux.md](termux.md) — device-side sshd (SSH probe in access_monitor)
- [control/tools/autojs6/](../../../control/tools/autojs6) — AutoJs6 deploy scripts
