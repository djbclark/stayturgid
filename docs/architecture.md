# Project architecture

stayturgid is organized around **where code runs**, not around Ansible alone.

## Top-level split

| Tree | Runs on | Purpose |
|------|---------|---------|
| `control/` | Mac control node | Operator scripts, shared Python, VLM sidecar, per-domain deploy tools |
| `device/` | Android phones | Termux runtime + AutoJs6 watchdog project |
| `catalogs/` | Repo data | Obtainium JSON catalogs (no executable code) |
| `ansible/` + `ansible_collections/` | Mac (deploy) | Idempotent fleet provisioning via Galaxy collections |
| `docs/` | — | Narrative docs, ADRs, module guides |
| `tests/` | Mac CI | Unit tests and device-tier harness |

## `control/`

- **`bin/`** — Long-running monitors, fleet deploy entrypoints, health checks (`deploy_fleet.py`, `check_fleet_health.py`, launchd-backed monitors).
- **`lib/`** — Shared Python imported by both `bin/` and `tools/` (adb resolution, screen control, a11y helpers, fleet profiles). Prefer `stayturgid_device.adb_bin()` for Mac adb (launchd-safe absolute path).
- **`vlm/`** — Optional UI-TARS vision sidecar for verification gates.
- **`tools/<domain>/`** — Focused Mac helpers (AutoJs6 deploy, Obtainium import, Play/Aurora, F-Droid) invoked by Ansible modules or operators.

## `device/`

- **`termux/`** — Boot scripts, repair loop, on-device Python (repo: `device/termux/`) deployed to `~/.stayturgid/`.
- **`autojs6/`** — Watchdog JavaScript project (repo: `device/autojs6/`) pushed to `/sdcard/stayturgid/autojs6/`.

## Runtime roots (single-root per filesystem)

| Filesystem | Root | Notes |
|------------|------|--------|
| Device shared storage | `/sdcard/stayturgid/` | Default: `autojs6/`, `state/`, `logs/`, `run/` |
| Fire OS Termux shared | `~/.stayturgid/shared` | Set via `STAYTURGID_SD` in `~/.stayturgid/env` |
| Termux private | `~/.stayturgid/` | `bin/`, `logs/`, `run/`, `state/` |
| Mac control node | `~/.config/stayturgid/` | `devices.conf`, `logs/`, `state/` |

On-device AutoJs6 project path is always **`/sdcard/stayturgid/autojs6/`** (not `…/device/autojs6/`).

## Deploy flow

```
make deploy
  → ansible/playbooks/site.yml
    → fleet/preflight.yml
    → fleet/bootstrap.yml (if needed)
    → fleet/fleet.yml (termux_userland, autojs6, obtainium, …)
    → fleet/post-ui.yml
    → fleet/validate.yml
    → control_node/site.yml (launchd agents on Mac)
```

Canonical playbooks live under `ansible/playbooks/fleet/` and
`ansible/playbooks/control_node/`. Flat `ansible/playbooks/*.yml` aliases were
removed (OPTIONS 62). Entry point remains `ansible/playbooks/site.yml`.

App stores (F-Droid / Play) are **parked** unless
`stayturgid_app_stores_enabled: true`.

## Path discovery

Scripts find the repo root via `control/lib/stayturgid_root.py` (markers:
`device/termux/` + `control/lib/`). Ansible uses `stayturgid_repo_root` in the
`control_node` role defaults.

## Soft health vs device health

- **Mac soft health:** launchd `com.stayturgid.fleet-health` →
  `control/bin/fleet_health_monitor.py` → `~/.config/stayturgid/logs/fleet-health.log`.
  Agents run `make health` at session start.
- **`SCRAPE_STALE`** can mean the **Mac probe** is broken (e.g. adb not on PATH),
  not only that the phone is dead — read the log line body.
- Launchd agents set `PATH` + `STAYTURGID_ADB` so Homebrew `adb` is found.

## Related docs

- [README.md](../README.md) — quick layout + getting started
- [handoff.md](handoff.md) — operator / agent session context
- [hacking.md](hacking.md) — device setup walkthrough
- [options.md](options.md) — open work (OPTIONS 62 shim cleanup closed when landed)
