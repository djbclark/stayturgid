# stayturgid

Keeps wireless ADB (port 5555), Shizuku, and SSH alive on **unrooted Android phones** across reboots, and makes them reachable over Tailscale via **ADB + SSH**. Each piece below is a **separate module** — use only what you need.

---

## Modules

| Module | Path | Standalone? | README |
|--------|------|-------------|--------|
| **Termux runtime** | `device/termux/` | Yes — repair, boot loop, presence | [docs/modules/termux.md](docs/modules/termux.md) |
| **Ansible deploy** | `ansible/` | Yes — Termux over SSH only | [ansible/README.md](ansible/README.md) |
| **Control node** | `control/bin/` | Yes — launchd reconnect + outage alert | [docs/modules/control.md](docs/modules/control.md) |
| **AutoJs6 watchdog** | `device/autojs6/` | Yes — needs Termux repair scripts | [docs/modules/autojs6.md](docs/modules/autojs6.md) |
| **Obtainium catalogs** | `catalogs/obtainium/` | Yes — any Obtainium user | [docs/modules/obtainium.md](docs/modules/obtainium.md) |
| **F-Droid / Neo Store** | `stayturgid.fdroid` collection | Parked — manual / `--scope fdroid` when re-enabled | [docs/modules/fdroid.md](docs/modules/fdroid.md) |
| **Play / Aurora Store** | `stayturgid.play` collection | Parked — manual / `--scope play` when re-enabled | [docs/modules/play.md](docs/modules/play.md) |
| **Shared libraries** | `control/lib/` | Yes — `resolve-adb`, UI parse, fleet health | [control/lib/README.md](control/lib/README.md) |

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/README.md](docs/README.md) | Documentation index |
| [docs/incubator/](docs/incubator/) | Parked side projects (Inferno, etc.) — do not implement |
| [docs/hacking.md](docs/hacking.md) | Developer setup, clean install, Obtainium, Termux swap |
| [docs/handoff.md](docs/handoff.md) | Maintainer / AI handoff — includes mandatory Mac fleet-health triage |
| [`.cursor/rules/`](.cursor/rules/) | **AI agent policies** (always-on; read on every handoff) — self-heal, screen-control hold, … |
| [human/HANDOFF-HUMAN.md](human/HANDOFF-HUMAN.md) | Operator tasks (credentials, deploy approval) — human-only |
| [docs/options.md](docs/options.md) | Next-work menu — agents append + push when operator asks for options |
| [version.json](version.json) | Repo release version (Ansible / manual deploy) |

---

## Full stack (quick path)

1. Shizuku (thedjchi fork) — TCP mode, wireless debugging
2. Termux + Termux:Boot + Termux:API — [docs/modules/termux.md](docs/modules/termux.md) or `./control/bin/deploy_termux.py <host>`
3. AutoJs6 watchdog — [docs/modules/autojs6.md](docs/modules/autojs6.md) (`control/tools/autojs6/setup_autojs6.py`, etc.)
4. Obtainium catalog — [docs/modules/obtainium.md](docs/modules/obtainium.md)
5. Control node — [docs/modules/control.md](docs/modules/control.md) (ADB reconnect + access monitor)

**One command (fleet):** `make deploy` — Termux, AutoJs6, Obtainium, Tailscale, optional ensure_apps.

(`./control/bin/deploy_fleet.py` is the same; `make help` lists all targets.)

Neo Store / Aurora Store are **parked** (not in active deploy); see [docs/modules/fdroid.md](docs/modules/fdroid.md) and [docs/modules/play.md](docs/modules/play.md) to re-enable.

**Partial re-runs:** `./control/bin/deploy_fleet.py --scope fdroid [host]` · `./control/bin/deploy_fleet.py --scope play [host]` (no-op while app stores are parked)

---

## How it works

After each cold reboot and PIN unlock:

1. **Shizuku** auto-starts via Wireless Debugging (TCP mode → port 5555).
2. **Termux:Boot** runs `~/.termux/boot/start-adb.sh` → `sshd` + 5-min self-heal + repair loop.
3. **AutoJs6** `main.js` (20 min + boot via `boot-launcher.js`) → `stayturgid_repair.py`, notifications, Shizuku UI repair if needed.

---

## SSH to Termux

```bash
ssh s24    # or: ssh p7a
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
    vlm/                    — UI-TARS sidecar
    tools/                  — per-domain Mac helpers (autojs6, obtainium, …)
  device/
    termux/                 — on-device Termux runtime (boot, py, bin)
    autojs6/                — AutoJs6 project (main.js, lib, scripts)
  catalogs/obtainium/       — Obtainium JSON catalogs
  ansible/                  — site playbooks, inventory, control_node role
  ansible_collections/      — stayturgid.* Galaxy collections
  examples/  tests/  human/
  version.json
```

---

## Tested on

- Google Pixel 7a, Samsung Galaxy S24 (SM-S921U1), Android 16
- Amazon Kindle Fire HD 8 (Fire OS 11) — see [docs/handoff.md](docs/handoff.md) for hd8 quirks
- Shizuku thedjchi fork · AutoJs6 6.7.0 · Termux GitHub-debug stack
