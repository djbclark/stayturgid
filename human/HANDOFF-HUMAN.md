# Human handoff — operator tasks

> **For AI agents:** Do not ask the operator to do inline chat steps that belong
> here — link to this file. After they update `RESPONSES.md`, re-read it and
> continue.
>
> **Index:** [human/README.md](README.md) · Agent context: [HANDOFF.md](../HANDOFF.md)
> · Open work: [OPTIONS.md](../OPTIONS.md)

Last updated: **2026-07-09 night** (Ansible Track B + Makefile ops)

---

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
| AutoJs6 drawer fleet profile | `shared/autojs6_drawer_defaults.json` + `enable_autojs6_shizuku.py` |
| AutoJs6 upstream API request | [AutoJs6 #553](https://github.com/SuperMonster003/AutoJs6/issues/553) |
| PiP / overlay clearance | `ScreenControlSession` clears YouTube PiP via `stack remove` (Samsung verified) |
| Accessibility list wipe fix | Drawer a11y toggle **removed**; merge-only via `mac/a11y_services.py` |
| p7a a11y restore | Profile merge restored Buzzkill / Notch / existing apps (6 services) |
| Aurora background dialog (hd8) | Historical — Aurora parked from fleet 2026-07-09 |
| Fleet deploy order | harden (core apps) → AutoJs6 enable (Aurora configure parked) |

**Operator check (optional):** On p7a, confirm Buzzkill / Notch / Wispr / Tasker / AutoInput
still work in Settings → Accessibility. If anything missing:

```bash
python3 mac/a11y_services.py show p7a
python3 mac/a11y_services.py restore p7a
```

---

## Priority 1 — Unblocks Play / Google download automation

### 1.1 Google Play credentials (optional)

**Why:** `stayturgid.play.play_apps` with `apkeep_source: google-play` or
`gplaycli` needs a Play session. apk-pure mirrors work without login but are flaky.

**You do:**

1. Choose one path:
   - **apkeep (recommended):** run
     `~/.venv-stayturgid-play/bin/python play/mac/obtain_play_aas.py -e you@gmail.com`
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

`./autojs6/mac/enable_autojs6_shizuku.py <host>` runs during fleet deploy and
`setup_autojs6.py`. Requires **unlocked screen** + Shizuku server for
`ScreenControlSession` consent (~10 s).

Record in `RESPONSES.md` only if it fails on a host.

### 2.1 Accessibility services (if wiped again)

**Never** use the AutoJs6 drawer accessibility toggle alone — it replaces the
entire system list. Fleet tooling uses merge-only writes.

```bash
python3 mac/a11y_services.py backup <host>   # snapshot live list
python3 mac/a11y_services.py restore <host>    # merge profile + backup + AutoJs6
```

Profiles: `shared/a11y_profiles.json`. See [HACKING.md](../HACKING.md) Part 5.

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

Before live `./mac/deploy_fleet.py` on **all** hosts:

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
- Optional Obtainium import: `obtainium/app-stores-optional.json`
- See [fdroid/README.md](../fdroid/README.md) and [play/README.md](../play/README.md)

### 4.1 Ansible Galaxy publish

Requires [galaxy.ansible.com](https://galaxy.ansible.com) API token. Not needed
for Git-tag installs. Note in `RESPONSES.md` if published.

### 4.2 Obtainium in-app confirm

Catalog apply uses `obtainium/mac/import_catalog.py` (screen control). Unlock
phone when deploy runs import.

### 4.3 Upstream tracking

- **AutoJs6 fleet config API:** [issue #553](https://github.com/SuperMonster003/AutoJs6/issues/553)
  — no non-UI drawer prefs on release builds today.

---

## Quick reference — env files (never commit)

| Purpose | Path |
|---------|------|
| Play apkeep | `~/.config/stayturgid/play.env` |
| gplaycli | `~/.config/gplaycli/gplaycli.conf` |
| ADB aliases | `~/.config/stayturgid/devices.conf` |
| A11y live backup | `shared/a11y_backups/<host>.txt` (gitignored) + `/sdcard/stayturgid/state/a11y_services_backup.txt` |

---

## When you're done

Copy `RESPONSES.md.example` → `RESPONSES.md`, fill in checkboxes, tell the agent:

> Read human/RESPONSES.md and continue.
