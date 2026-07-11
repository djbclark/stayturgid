# Human handoff — operator tasks

> **For AI agents:** Do not ask the operator to do inline chat steps that belong
> here — link to this file. After they update `RESPONSES.md`, re-read it and
> continue.
>
> **Index:** [human/README.md](README.md) · Agent context: [docs/handoff.md](../docs/handoff.md)
> · Open work: [docs/options.md](../docs/options.md)

Last updated: **2026-07-10 afternoon** (review fixes + Fire wireless-debug self-heal + handoff)

---

## Session notes (2026-07-10 evening) — agent completed

| Area | Status |
|------|--------|
| Code/docs review follow-through | H1/M1–M6 + L1–L9 on `master`; pytest green |
| Fire wireless debugging | Mac `fire_help` re-asserts `adb_wifi_enabled`; resolve prefers mDNS |
| hd8 AutoJs6 “Save main.js” dialog | Caused by wrong `termux-open` path — use `start_watchdog.py` only |
| `make health` | **OK** s24/p7a/hd8 at handoff write (hd8 soft health often SSH) |
| Live full-fleet soak | **Still optional** — announce before `make deploy` / `make verify` |

**Operator (only if Mac agents still old):** after pull, optional `make deploy-mac` to reload launchd with latest `fire_help_monitor`.

## Session notes (2026-07-10 afternoon) — agent completed

| Area | Status |
|------|--------|
| Senior review fixes | H1–H3, OPTIONS 62, module docs, lint green |
| Mac fleet-health adb PATH | Launchd plists patched + reloaded; `make health` OK for s24/p7a/hd8 |
| `make deploy-check HOSTS=s24` | Pass (`failed=0`) after `stayturgid_repo_root` fix |
| Live soak | **Still needed** — announced `make deploy` + `make verify` |

## Session notes (2026-07-10) — agent completed

| Area | Status |
|------|--------|
| Repo restructure | `control/`, `device/`, `catalogs/`, `docs/` on `master`; pushed to GitHub |
| Path consistency | On-device `/sdcard/stayturgid/autojs6/`; `control/lib` imports; canonical Ansible playbooks |
| OPTIONS 62 | **Closed 2026-07-10** — flat playbook shims removed; keep `site.yml` + `fleet/` + `control_node/` |
| Fleet soak post-reorg | **Not run** — see below |

**Operator check (recommended before relying on fleet):**

```bash
make health                    # expect hd8 SCRAPE_STALE possible; p7a/s24 should be OK
make deploy-check HOSTS=s24    # dry-run after reorg
# optional live soak (announce first):
# make deploy HOSTS=s24 && make verify HOSTS=s24
```

Confirm Mac LaunchAgents still point at `control/bin/` (should already — reorg kept paths).

## Session notes (2026-07-09 night) — agent completed

These do **not** need operator action unless noted.

| Area | Status |
|------|--------|
| Ansible validate + preflight | `stayturgid.fleet.validate`, `preflight.yml` in `site.yml`; SSH preflight out of `deploy_fleet.py` |
| hd8 AutoJs6 deploy | `autojs6_project_deploy` module — full fleet path on Fire OS |
| Makefile ops | `make help` (default), `make deploy`, `make health`, etc. |
| Fleet health triage | Stale morning s24 LOST no longer fails `make health` when host is OK now |
| Neo/Aurora | Still **parked** — no operator action to unpark |

**Operator check (optional):** `make health` at session start; `make deploy HOSTS=s24` only when you want a live soak (announce first).

## Session notes (2026-07-09) — agent completed

| Area | Status |
|------|--------|
| On-device Obtainium / AutoJs6 UI | Termux scripts via `localhost:5555`; Mac wrappers SSH-first with Mac adb fallback (hd8 Mac-only) |
| Screen-control gate | Obtainium / AutoJs6 installer taps use `session.shell` |
| shell-gpt / local LLM | Documented as OPTIONS track **E** — not implemented |

## Session notes (2026-07-08) — agent completed

These do **not** need operator action unless noted.

| Area | Status |
|------|--------|
| AutoJs6 fleet profile | `device/autojs6/fleet_profile.json` + `FleetProfileActivity` intent |
| AutoJs6 fleet API | [issue #553](https://github.com/SuperMonster003/AutoJs6/issues/553), [djbclark/AutoJs6](https://github.com/djbclark/AutoJs6/releases) |
| PiP / overlay clearance | `ScreenControlSession` clears YouTube PiP via `stack remove` (Samsung verified) |
| Accessibility list wipe fix | Drawer a11y toggle **removed**; merge-only via `control/bin/a11y_services.py` |
| p7a a11y restore | Profile merge restored Buzzkill / Notch / existing apps (6 services) |
| Aurora background dialog (hd8) | Historical — Aurora parked from fleet 2026-07-09 |
| Fleet deploy order | harden (core apps) → AutoJs6 enable (Aurora configure parked) |

**Operator check (optional):** On p7a, confirm Buzzkill / Notch / Wispr / Tasker / AutoInput
still work in Settings → Accessibility. If anything missing:

```bash
python3 control/bin/a11y_services.py show p7a
python3 control/bin/a11y_services.py restore p7a
```

---

## Priority 1 — Unblocks Play / Google download automation

### 1.1 Google Play credentials (optional)

**Why:** `stayturgid.play.play_apps` with `apkeep_source: google-play` or
`gplaycli` needs a Play session. apk-pure mirrors work without login but are flaky.

**You do:**

1. Choose one path:
   - **apkeep (recommended):** run
     `~/.venv-stayturgid-play/bin/python control/tools/play/obtain_play_aas.py -e you@gmail.com`
     (first time: `python3 -m venv ~/.venv-stayturgid-play && ~/.venv-stayturgid-play/bin/pip install browser-cookie3`).
     Click **I agree** on EmbeddedSetup; ignore the forever spinner. Helper writes
     `~/.config/stayturgid/play.env`. Then `source ~/.config/stayturgid/play.env`.
   - **gplaycli:** copy `play/gplaycli.conf.example` →
     `~/.config/gplaycli/gplaycli.conf` and set an app password — often
     `BadAuthentication` now; prefer apkeep.
2. In `RESPONSES.md`, note which path you chose and that creds are in place
   (do not paste tokens).

**Agent can then:** test `play_store` / `ensure_apps` with `source: play` on a dev app.

---

## Priority 2 — On-device one-time setup (if not already done)

### 2.0 AutoJs6 fleet drawer + Shizuku (mostly automated)

`./control/tools/autojs6/enable_autojs6_shizuku.py <host>` runs during fleet deploy and
`setup_autojs6.py`. Requires **unlocked screen** + Shizuku server for
`ScreenControlSession` consent (~10 s).

Record in `RESPONSES.md` only if it fails on a host.

### 2.1 Accessibility services (if wiped again)

**Never** use the AutoJs6 drawer accessibility toggle alone — it replaces the
entire system list. Fleet tooling uses merge-only writes.

```bash
python3 control/bin/a11y_services.py backup <host>   # snapshot live list
python3 control/bin/a11y_services.py restore <host>    # merge profile + backup + AutoJs6
```

Profiles: `control/lib/a11y_profiles.json`. See [docs/hacking.md](../docs/hacking.md) Part 5.

---

## Priority 3 — Fleet deploy approval

### 3.1 Device reachability (2026-07-08)

| Host | Mac adb | Notes |
|------|---------|-------|
| **s24** | USB wireless-debug or Tailscale | Lab reference; PiP clearance tested |
| **p7a** | mDNS / Tailscale | May be adb-offline when Tailscale down — USB or open Tailscale |
| **hd8** | **USB** `GN43T503430603PS` preferred | Fire OS; no Termux localhost:5555 loopback |

When **hd8** and **s24** are on USB, agents should use `resolve_adb` (USB wins
when online).

### 3.2 hd8 USB bootstrap

Fire OS still needs occasional **USB** for Mac adb when wireless is flaky.
AutoJs6 project push uses adb; Termux deploy uses SSH.

### 3.3 Production deploy go/no-go

Before live `./control/bin/deploy_fleet.py` on **all** hosts:

- **Unlock screen** on each host during post-Ansible steps (Obtainium import,
  AutoJs6 drawer automation).
- hd8/s24 on USB if wireless adb is down.
- Obtainium catalog import is interactive (screen control).

Answer in `RESPONSES.md`:

`deploy_fleet: approved | hold | s24-only | hd8-only | p7a-only`

---

## Priority 4 — Optional / later

### 4.0 Neo Store + Aurora (parked)

Fleet no longer installs, configures, or health-checks Neo Store or Aurora.
Apps may remain on devices from earlier deploys. To use again:

- Set `stayturgid_app_stores_enabled: true` in `ansible/inventory/group_vars/stayturgid.yml`
- Optional Obtainium import: `catalogs/obtainium/app-stores-optional.json`
- See [docs/modules/fdroid.md](../docs/modules/fdroid.md) and [docs/modules/play.md](../docs/modules/play.md)

### 4.1 Ansible Galaxy publish

Requires [galaxy.ansible.com](https://galaxy.ansible.com) API token. Not needed
for Git-tag installs. Note in `RESPONSES.md` if published.

### 4.2 Obtainium in-app confirm

Catalog apply uses `control/tools/obtainium/import_catalog.py` (screen control). Unlock
phone when deploy runs import.

### 4.3 Upstream tracking

- **AutoJs6 fleet config API:** [issue #553](https://github.com/SuperMonster003/AutoJs6/issues/553)
  — implemented in [djbclark/AutoJs6](https://github.com/djbclark/AutoJs6/releases) (FleetProfileActivity intent).

---

## Quick reference — env files (never commit)

| Purpose | Path |
|---------|------|
| Play apkeep | `~/.config/stayturgid/play.env` |
| gplaycli | `~/.config/gplaycli/gplaycli.conf` |
| ADB aliases | `~/.config/stayturgid/devices.conf` |
| A11y live backup | `control/lib/a11y_backups/<host>.txt` (gitignored) + `/sdcard/stayturgid/state/a11y_services_backup.txt` |

---

## When you're done

Copy `RESPONSES.md.example` → `RESPONSES.md`, fill in checkboxes, tell the agent:

> Read human/RESPONSES.md and continue.
