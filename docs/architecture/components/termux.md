# Termux layer — boot scripts, repair, presence

Scripts that run **on the phone** inside Termux. Usable without AutoJs6 or Ansible if you deploy manually.

**Full project:** [../../README.md](../../README.md)

## What this module does

| Piece                                         | Role                                                                                                |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `stayturgid_repair.py`                        | Self-heal sshd, localhost:5555 ADB, Shizuku, phone→Mac ET SSH config; prints `STATUS …` for callers |
| `bridges.py --mode repair`                    | Polls `/sdcard/stayturgid/run/repair_now`; runs repair within ~2s (AutoJs6 fallback)                |
| `stayturgid_agent_presence.py`                | Torch/notification + `request-screen` / `gate` / `on`/`off`                                         |
| `stayturgid_import_catalog.py` etc.           | On-device post-UI (Obtainium / Aurora / AutoJs6) via `localhost:5555`                               |
| `stayturgid_screen_control.py`                | On-device consent + inversion gate (same policy as Mac `ScreenControlSession`)                      |
| `check-repo-version` / battery / screen-awake | Python under `~/.stayturgid/bin/` (see `py/`)                                                       |
| `boot/start-adb.sh`                           | Termux:Boot: sshd, wake-lock, 5-min self-heal loop, battery tier check                              |
| `boot/start-repair-bridge.sh`                 | Starts `bridges.py --mode repair` at boot                                                           |
| `boot/start-autojs6-watchdog.sh`              | Launches AutoJs6 `boot-launcher.js` after boot                                                      |

### Presence / consent fail modes (caller choice)

| Action                           | Timeout / missing script                                            | Intended policy                                      |
| -------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------- |
| `request-screen`                 | Some Mac callers treat timeout as fail-**open** (proceed with care) | Soft ask before long batches; not a hard safety gate |
| `gate` / consent dialog          | Fail-**closed** (exit 75)                                           | Human denial or timeout → **do not** take glass      |
| `on` / presence missing (rc 127) | Fail-**closed**                                                     | Never leave inversion on without presence            |

Agents: prefer fail-closed for any path that enables inversion or `adb input`.
Document which path you use if you wrap presence yourself.

All deployable tools land under **`~/.stayturgid/bin/`** (not `~/`).

## Standalone use

**Minimum on device:** Termux (GitHub-signed), Termux:Boot, Termux:API, Shizuku with TCP mode (port 5555), `android-tools` in Termux.

```bash
mkdir -p ~/.stayturgid/bin ~/.termux/boot
cp device/termux/py/stayturgid_repair.py \
   device/termux/py/stayturgid_agent_presence.py \
   device/termux/py/stayturgid_bridges.py \
   ~/.stayturgid/bin/
cp device/termux/boot/*.sh ~/.termux/boot/
chmod +x ~/.stayturgid/bin/* ~/.termux/boot/*.sh
# Prefer lineinfile / Ansible for this key; do not clobber user properties:
grep -q '^allow-external-apps=true' ~/.termux/termux.properties 2>/dev/null \
  || echo 'allow-external-apps=true' >> ~/.termux/termux.properties

pkg update && pkg upgrade -y && pkg install -y openssh android-tools termux-api runit et
sshd
```

Open **Termux:Boot** once after install. `start-adb.sh` runs repair every 5 min; for watchdog notifications and Shizuku UI repair, add [AutoJs6](autojs6.md).

**Phone → Mac Eternal Terminal:** fleet deploy installs `Host mac` SSH config
(passphrase-less `id_ed25519_fleet`) and the `et` package. From Termux:
`et mac` or `et -c 'hostname' mac`. Control-node keys and docs:
[control.md § Phone → Mac Eternal Terminal](control.md).

**Low-battery alarm:** `stayturgid_battery_alarm.py` runs every 5 min from the boot loop. While discharging, fires **once per tier**: 30%, 25%, 20%, 15%, 10%, 5%, then each 1% below 5 (when several tiers are crossed at once — e.g. first run at low battery — only the lowest fires; higher tiers are marked done). Each tier blinks the screen a solid color (purple @30 → red @5+) with brightness pulses; from 15% also pulses the flashlight (count matches tier). During DND/silent ringer: screen blink + one quick torch only (no toast/vibrate). Resets when charging or above 30%. Requires Termux:API + color PNGs in `~/.stayturgid/battery-colors/` (deployed by Ansible).

**Repo version check:** `stayturgid_check_repo_version.py` runs at most once per day from the boot loop (notify only; deploy from Mac).

**Callers:** [AutoJs6](autojs6.md) (`RUN_COMMAND` → `stayturgid_repair.py`), [Ansible](../../ansible/README.md) over SSH.

## Deploy with Ansible (recommended)

Deploys Python runtime under `~/.stayturgid/bin/`, bridge shells, and boot hooks.

```bash
./control/bin/deploy_termux.py s24   # or p7a
```

## Package updates (standard Termux + fleet schedule)

Termux’s package manager is **`pkg`** (thin wrapper over apt). The supported
unattended maintenance commands are:

```bash
pkg update
pkg upgrade -y
# equivalent under the hood: apt-get update / apt-get full-upgrade
```

stayturgid uses the **`stayturgid.termux.termux_pkg`** module for this (same as
deploy): pin mirror → `pkg update` → `apt-get full-upgrade` / `pkg upgrade -y`
→ re-pin mirror (`packages-cf.termux.dev`).

**Nightly (all inventory hosts):** Mac launchd
`com.stayturgid.termux-pkg-nightly` (default **04:15 local**) runs:

```bash
python3 control/bin/termux_pkg_nightly.py
# → ansible/playbooks/fleet/termux-pkg-upgrade.yml
```

```bash
just termux-pkg-upgrade              # run now, all hosts
just --set hosts s24 termux-pkg-upgrade    # one host
just termux-pkg-upgrade (--check via just)      # dry run
just deploy-mac                      # install/reload the launchd agent
```

| Var                                              | Default    | Meaning                             |
| ------------------------------------------------ | ---------- | ----------------------------------- |
| `stayturgid_termux_pkg_nightly_enabled`          | `true`     | Install launchd agent on Mac        |
| `stayturgid_termux_pkg_nightly_hour` / `_minute` | `4` / `15` | Mac local time                      |
| `stayturgid_termux_pkg_upgrade_enabled`          | `true`     | Per-host skip in the playbook       |
| `stayturgid_termux_pkg_upgrade_serial`           | `1`        | Ansible serial (one host at a time) |

Logs: `~/.config/stayturgid/logs/termux-pkg-nightly.log`.

On-device cron/`termux-job-scheduler` is **not** used: fleet control is already
Mac→SSH Ansible, which keeps mirror pinning and failure logs in one place.

## Logs and status

```bash
~/.stayturgid/bin/stayturgid_repair.py
tail -f ~/.stayturgid/logs/repair.log
tail -f /sdcard/stayturgid/logs/watchdog.log
```

## Presence protocol

```bash
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py request-screen "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py on  "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py off "Galaxy S24" Auto'
ssh s24 '~/.stayturgid/bin/stayturgid_agent_presence.py status'
```

## Related docs

- [docs/hacking.md §1.4](../hacking.md) — manual Termux setup
- [docs/handoff.md](../handoff.md) — repair architecture
- [docs/research/experiments/on-device-llm.md](../research/experiments/on-device-llm.md) — optional shell-gpt escalation (not hot-path)
- [docs/architecture/components/autojs6.md](autojs6.md) — watchdog layer
