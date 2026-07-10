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
- **`lib/`** — Shared Python imported by both `bin/` and `tools/` (adb resolution, screen control, a11y helpers, fleet profiles).
- **`vlm/`** — Optional UI-TARS vision sidecar for verification gates.
- **`tools/<domain>/`** — Focused Mac helpers (AutoJs6 deploy, Obtainium import, Play/Aurora, F-Droid) invoked by Ansible modules or operators.

## `device/`

- **`termux/`** — Boot scripts, repair loop, on-device Python (repo: `device/termux/`) deployed to `~/.stayturgid/`.
- **`autojs6/`** — Watchdog JavaScript project (repo: `device/autojs6/`) pushed to `/sdcard/stayturgid/autojs6/`.

## Deploy flow

```
make deploy
  → ansible/playbooks/site.yml
    → termux_userland (device/termux → phone)
    → autojs6_watchdog (device/autojs6 → phone)
    → obtainium / play / fdroid roles (catalogs + control/tools)
  → control_node role (control/bin launchd agents on Mac)
```

## Path discovery

Scripts find the repo root via `control/lib/stayturgid_root.py` (markers: `device/termux/` + `control/lib/`). Ansible uses `stayturgid_repo_root` in the `control_node` role defaults.

## Related docs

- [README.md](../README.md) — quick layout + getting started
- [handoff.md](handoff.md) — operator / agent session context
- [hacking.md](hacking.md) — device setup walkthrough
