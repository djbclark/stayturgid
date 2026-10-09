<p align="center">
  <img src="docs/assets/logo.png" alt="stayturgid logo" width="200">
</p>

# stayturgid

> **AI coding agents:** start at [AGENTS.md](AGENTS.md) instead of this file —
> it's the entry point with conventions, commands, and current state (also see
> [docs/STATUS.md](docs/STATUS.md) for the dated fleet/workstream snapshot).

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on **unrooted Android phones** across reboots, and makes them reachable over Tailscale via **ADB + SSH**. Each piece below is a **separate module** — use only what you need.

---

## Modules

| Module                        | Path                                                                       | Standalone?                                      | README                                                                                                                     |
| ----------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **Termux runtime**            | `device/termux/`                                                           | Yes — repair, boot loop, presence                | [docs/architecture/components/termux.md](docs/architecture/components/termux.md)                                           |
| **Ansible deploy**            | `ansible/`                                                                 | Yes — Termux over SSH only                       | [ansible/README.md](ansible/README.md)                                                                                     |
| **Control node**              | `control/bin/`                                                             | Yes — launchd reconnect + outage alert           | [docs/architecture/components/control.md](docs/architecture/components/control.md)                                         |
| **Native agent**              | `device/native-agent/`                                                     | Yes — Kotlin APK, Shizuku-gated                  | [device/native-agent/README.md](device/native-agent/README.md)                                                             |
| **FIRERPA failsafe**          | `ansible_collections/stayturgid/firerpa/`                                  | Yes — optional gRPC backup channel               | [docs/research/evaluations/firerpa-install-map-2026-07-12.md](docs/research/evaluations/firerpa-install-map-2026-07-12.md) |
| **SSH Certificate Authority** | `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml` | Yes — fleet host-key trust                       | [tasks/ca.yml](ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml); `just ca-status`                 |
| **Play**                      | `stayturgid.play` collection                                               | Parked — manual / `--scope play` when re-enabled | [docs/architecture/components/play.md](docs/architecture/components/play.md)                                               |
| **Shared libraries**          | `control/lib/`                                                             | Yes — `resolve-adb`, UI parse, fleet health      | [control/lib/README.md](control/lib/README.md)                                                                             |

---

## Documentation

| Document                                                                                     | Purpose                                                                                                                                    |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| [AGENTS.md](AGENTS.md)                                                                       | Start here (AI agents) - conventions, commands, condensed current state, full doc map                                                      |
| [docs/STATUS.md](docs/STATUS.md)                                                             | Dated snapshot: fleet health, active workstreams, operator-action queue, known gotchas                                                     |
| [docs/README.md](docs/README.md)                                                             | Full documentation index                                                                                                                   |
| [docs/research/experiments/](docs/research/experiments/)                                     | Parked side projects - do not implement unless revived ([tablet-control](docs/research/experiments/tablet-control-phone.md), Inferno, ...) |
| [docs/hacking.md](docs/hacking.md)                                                           | Developer setup, clean install, Termux swap                                                                                                |
| [docs/coding-rules.md](docs/coding-rules.md)                                                 | Durable coding, safety, testing, Git, and completion rules                                                                                 |
| [docs/rules/](docs/rules/)                                                                   | AI agent policies (always-on) - normal-deploy convergence, self-heal, screen-control hold, GitHub-issues hygiene                           |
| [docs/options.md](docs/options.md)                                                           | Strategic/deferred work menu with stable IDs (discrete bugs live in GitHub issues)                                                         |
| [dashboard-framework research prompt](docs/research/prompts/dashboard-framework-research.md) | Self-contained brief for evaluating dashboard / ops frameworks                                                                             |
| [docs/archive/](docs/archive/)                                                               | Superseded plans and old sessions - historical record only, not current work order                                                         |
| [version.json](version.json)                                                                 | Repo release version (Ansible / manual deploy)                                                                                             |

---

## Full stack (quick path)

1. Shizuku (ShizukuTendCF / frdminc fork) — TCP mode, wireless debugging
2. Termux + Termux:Boot + Termux:API — [docs/architecture/components/termux.md](docs/architecture/components/termux.md) or `./control/bin/deploy_termux.py <host>`
3. Native agent — `just agent-rollout <host>` (`device/native-agent/`, Kotlin APK)
4. Control node — [docs/architecture/components/control.md](docs/architecture/components/control.md) (ADB reconnect + access monitor)

**One command (fleet):** `just deploy` — Termux, native-agent Shizuku grant, Tailscale, optional ensure_apps.

(`./control/bin/deploy_fleet.py` is the same; `just --list` lists all targets.)

Play download automation is **parked** (not in active deploy); see [docs/architecture/components/play.md](docs/architecture/components/play.md) to re-enable.

**Partial re-runs:** `./control/bin/deploy_fleet.py --scope play [host]`

The fleet dashboard is available on the control node at `http://127.0.0.1:4097/`
(normally reached through the configured HTTPS proxy). A device card with a
`shizuku_down` issue includes an **open Shizuku and test rish** action. Android
still requires the operator to choose **Allow all the time**; success is verified
only when `~/.stayturgid/bin/rish -c 'id -u'` returns UID 2000. See
[the control-node guide](docs/architecture/components/control.md#dashboard-shizuku-authorization-h8).

### Maintainer resume order

Before selecting new work, read [docs/STATUS.md](docs/STATUS.md) for current
state, then check the highest-priority open
[GitHub issue](https://github.com/djbclark/stayturgid/issues) or
[docs/options.md](docs/options.md) entry unless the operator names a
different item. Current reliability work takes precedence over optional
Galaxy publishing, LLM, FIRERPA MCP/WebRTC/MITM, and command-runner
enhancements.

---

## How it works

After each cold reboot and PIN unlock:

1. **Shizuku** auto-starts via Wireless Debugging (TCP mode → port 5555).
2. **Termux:Boot** runs the compatibility entrypoint
   `~/.termux/boot/start-adb.sh`, which immediately delegates to Python
   `start_adb.py` → `sshd` + 5-min self-heal + repair loop.
3. **Native agent** (`org.stayturgid.agent`, `device/native-agent/`) runs as a
   foreground service, launched/kept alive via Shizuku, doing its own
   liveness + catastrophic-repair loop independent of Termux.

---

## SSH to Termux

```bash
ssh oneui-device    # or: ssh stock-android-device
```

Requires SSH keys on the Mac control node (`~/.ssh/*.pub` auto-synced to every device; bootstrap with `./control/bin/bootstrap_ssh.py` when SSH is not up yet). Tailscale or `adb forward tcp:8022 tcp:8022`. See [docs/hacking.md](docs/hacking.md).

---

## Keyguard-proof sshd recovery (Tasker)

When Android kills every Termux process and the keyguard is locked, the only
recovery that needs no unlock is a broadcast from the Mac:
`adb shell am broadcast -a com.stayturgid.SSHD_RECOVER` → Tasker profile →
Termux `RunCommandService` → `~/.termux/tasker/sshd-recover-tasker.sh` (the
dispatcher) → every executable in `~/.termux/tasker/recover.d/`, of which
`10-sshd` runs `sshd-recover.sh` (starts `runsvdir` if dead, then `sv up sshd`).
Tasker is in the middle because the adb shell UID lacks
`com.termux.permission.RUN_COMMAND`; Tasker holds it. Background:
[docs/options.md](docs/options.md) item 44.

`fleet_health_monitor.py` fires the broadcast itself whenever SSH fails but adb
still answers (or the probe sees `sshd=down`), at most every 10 minutes, and
logs `sshd-recover broadcast` in `~/.config/stayturgid/logs/fleet-health.log`.
`STAYTURGID_SKIP_WATCHDOG_HEAL=1` turns that off.

`just deploy` installs Termux:Tasker, the `~/.termux/tasker/` scripts and
`allow-external-apps=true`, and grants Tasker the `RUN_COMMAND` permission
(`control/lib/fleet_app_profiles.json`).

**Manual step, once per phone: install the Tasker project.** Nothing in the
deploy can do this; until it is done the recovery does not work and
fleet-health nags daily.

1. Copy [`device/tasker/StayTurgid_SSHD_Recover.prj.xml`](device/tasker/StayTurgid_SSHD_Recover.prj.xml)
   to `/sdcard/Tasker/projects/` (`adb push` works).
2. In Tasker, long-press a project tab → Import Project → pick the file. If no
   project tabs show, turn off Preferences → UI → Beginner Mode.
3. Check the profile "StayTurgid SSHD Recover" is switched on, then leave
   Tasker (it applies changes, and runs profiles, only once its editor is closed).
4. Run the test below.

The project never needs re-importing: the script it calls is a frozen
dispatcher, and new recoveries are added as files in `recover.d/`.

To build the same thing by hand instead of importing:

1. **Profile:** Event → System → Intent Received, Action `com.stayturgid.SSHD_RECOVER`.
2. **Task:** System → Send Intent with
   - Action: `com.termux.RUN_COMMAND`
   - Package: `com.termux`
   - Class: `com.termux.app.RunCommandService`
   - Extra: `com.termux.RUN_COMMAND_PATH:/data/data/com.termux/files/home/.termux/tasker/sshd-recover-tasker.sh`
   - Extra: `com.termux.RUN_COMMAND_BACKGROUND:true`
   - Target: Service

Point it at the dispatcher `sshd-recover-tasker.sh`, not `sshd-recover.sh`: it
stamps `~/.stayturgid/state/tasker-sshd-recover.ts` first, which is how the Mac
knows the Tasker path specifically works.

**Once imported, the Tasker project never changes.** Both script names are a
frozen interface: the Tasker task names `sshd-recover-tasker.sh`, and the native
agent APK and `firerpa_heal.py` name `sshd-recover.sh`. Deploys never delete, so
a renamed script would leave old phones running a stale copy;
`tests/python/test_tasker_frozen_paths.py` fails if either name changes. Each
run of the dispatcher:

1. writes line 1 of `tasker-sshd-recover.ts` as a bare epoch (the Mac reads
   line 1 only);
2. takes a `mkdir` lock (stale once its owner is dead or 15 minutes old) and
   skips the run if the last one started under 30 seconds ago, since any app
   can send the broadcast;
3. takes the Termux wake lock (`timeout 5 termux-wake-lock`), which nothing
   else restores after Android kills Termux;
4. runs every executable in `recover.d/` in name order, each under its own
   60-second timeout, and a failing entry does not stop the rest;
5. writes `~/.stayturgid/state/tasker-sshd-recover.result`: `end=` epoch,
   overall `exit=`, one `step.<name>=` exit code per entry, `sv_sshd=` (the
   `sv status sshd` line) and `tty=` (a pty there means Termux ignored
   `RUN_COMMAND_BACKGROUND`). Its log is `~/.stayturgid/logs/tasker-recover.log`.

**Add future recoveries as `recover.d/` files, never as new Tasker profiles.**
Drop an idempotent executable (mode 0755 in git) into
`device/termux/tasker/recover.d/` named `NN-what`; `just deploy` ships it and
prunes entries removed from the repo. `sshd-recover.sh` itself exits non-zero
unless `sv status sshd` shows `run:` after a bounded wait, and serialises its
`runsvdir` check-then-start with the boot script through the shared
`recover-lock.sh`.

**Test:** `adb -s <serial> shell am broadcast -a com.stayturgid.SSHD_RECOVER`,
then on the phone `cat ~/.stayturgid/state/tasker-sshd-recover.ts` shows a fresh
epoch and `cat ~/.stayturgid/state/tasker-sshd-recover.result` shows `exit=0`.

**Nag:** `control/bin/fleet_health_monitor.py` (every 5 min) reports the stamp's
age as `tasker_recover_age`. If it is missing or older than 7 days on a phone
with Tasker installed, the monitor fires the broadcast itself (at most hourly);
if the stamp is still stale on a later pass, it sends a Hermes notice
"stayturgid: action needed" and a WARNING in
`~/.config/stayturgid/logs/fleet-health.log`, at most daily, until the profile
works. It nags the same way, also at most daily, when
`tasker_recover_result=failed` (the last dispatcher run reached Termux but a
recovery failed) and when `tasker_monitor=stopped` (Tasker is installed but
its MonitorService is not running, so the broadcast is silently dropped).
All of these are advisory only: none counts as a health issue.

The native agent (0.9.12+) has its own leg that needs no Tasker profile: when
its co-monitor sees `sshd=down` on two consecutive probes it sends the same
`RUN_COMMAND` itself, at most every 5 minutes, and logs `[agent] sshd-recover`
to `agent.log`.

---

## Repo layout

```
stayturgid/
  README.md
  docs/                     — narrative docs + ADRs + module READMEs (+ architecture.md)
  control/
    bin/                    — operator scripts (deploy, monitors, verify)
    lib/                    — shared Python + fleet JSON profiles
    tools/                  — per-domain Mac helpers (native-agent, play, fdroid, …)
  device/
    termux/                 — on-device Termux runtime (boot, py, bin)
    native-agent/           — native Kotlin agent APK (K1)
  ansible/                  — site playbooks, inventory, control_node role
  ansible_collections/      — stayturgid.* Galaxy collections
  examples/  tests/  human/
  version.json
```

---

## Tested on

- Google Pixel 7a, Samsung Galaxy S24 (SM-S921U1), Android 16
- Amazon Kindle Fire HD 8 (Fire OS 11) — see [docs/research/fire-os-local-adb.md](docs/research/fire-os-local-adb.md) for fireos-device quirks
- Shizuku ShizukuTendCF (frdminc fork) · native-agent (Kotlin) · Termux GitHub-debug stack
