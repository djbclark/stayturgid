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
| **Native agent**              | `device/native-agent/`                                                     | Yes — Kotlin APK, Shizuku-gated                  | [docs/architecture/components/autojs6.md](docs/architecture/components/autojs6.md) (K1 cutover context)                    |
| **FIRERPA failsafe**          | `ansible_collections/stayturgid/firerpa/`                                  | Yes — optional gRPC backup channel               | [docs/research/evaluations/firerpa-install-map-2026-07-12.md](docs/research/evaluations/firerpa-install-map-2026-07-12.md) |
| **SSH Certificate Authority** | `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/ca.yml` | Yes — fleet host-key trust                       | [docs/handoff.md § Major changes](docs/handoff.md)                                                                         |
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
| [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md)                                             | Operator tasks (credentials, deploy approval) - human-only                                                                                 |
| [docs/options.md](docs/options.md)                                                           | Strategic/deferred work menu with stable IDs (discrete bugs live in GitHub issues)                                                         |
| [dashboard-framework research prompt](docs/research/prompts/dashboard-framework-research.md) | Self-contained brief for evaluating dashboard / ops frameworks                                                                             |
| [docs/archive/](docs/archive/)                                                               | Superseded plans and old sessions - historical record only, not current work order                                                         |
| [version.json](version.json)                                                                 | Repo release version (Ansible / manual deploy)                                                                                             |

---

## Full stack (quick path)

1. Shizuku (thedjchi fork) — TCP mode, wireless debugging
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
- Amazon Kindle Fire HD 8 (Fire OS 11) — see [docs/handoff.md](docs/handoff.md) for fireos-device quirks
- Shizuku thedjchi fork (djbclark fork) · native-agent (Kotlin) · Termux GitHub-debug stack
