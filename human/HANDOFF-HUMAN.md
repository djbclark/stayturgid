# HANDOFF — tasks for a human

> **For AI agents:** Do not ask the operator to do anything listed here inline in
> chat — point them to this file. After they update `RESPONSES.md`, re-read it
> and continue.

Last updated: 2026-07-07 (after Ansible collection v1.4.0 / fleet v1.5.0)

---

## Priority 1 — Unblocks Play / Google download automation

### 1.1 Google Play credentials (optional)

**Why:** `stayturgid.play.play_apps` with `apkeep_source: google-play` or
`gplaycli` needs a Play session. apk-pure mirrors work without login but are flaky.

**You do:**

1. Choose one path:
   - **apkeep:** export `GPLAY_EMAIL` and `GPLAY_AAS_TOKEN` (or `GPLAY_AUTH_TOKEN`)
     in your shell profile or `~/.config/stayturgid/play.env` (not in git).
   - **gplaycli:** copy `play/gplaycli.conf.example` →
     `~/.config/gplaycli/gplaycli.conf` and set an app password / token per
     [play/README.md](../play/README.md).
2. In `human/RESPONSES.md`, note which path you chose and that creds are in place
   (do not paste tokens).

**Agent can then:** test `play_store` / `ensure_apps` with `source: play` on a dev app.

---

## Priority 2 — On-device one-time setup (if not already done)

### 2.1 Neo Store (F-Droid)

After `./mac/deploy-fleet.sh <host>` (or `./mac/deploy-fdroid.sh <host>`):

1. Open Neo Store → Settings → Installer → **Shizuku**.
2. Enable **automatic / background updates**.

Record in `RESPONSES.md`: host + done/not done.

### 2.2 Aurora Store (Play)

After `./mac/deploy-fleet.sh <host>` (runs Aurora UI automation; or `./mac/deploy-play.sh <host>`):

1. Confirm Aurora Settings → Installer = Shizuku, automatic updates on.
2. If Aurora was installed outside fleet deploy, you may still need the Shizuku installer selection manually.

Record in `RESPONSES.md`: host + done/not done.

---

## Priority 3 — Fleet deploy approval

### 3.1 p7a verify follow-up (historical — agents prefer s24 for new tests)

Script drift is **fixed** (deploy ran 2026-07-07; `deployed termux scripts match repo` passes).
For new single-host checks, agents should use **s24** first (see HANDOFF.md).

Remaining verify items on p7a (agent cannot fix without device interaction):

| Check | Status | Notes |
|-------|--------|-------|
| AutoJs6 watchdog alive | FAIL | Stale after deploy — may need unlocked screen + a11y binding |
| Termux mirror pinned | FAIL | Investigate mirror task / host state |
| Boot-loop restart handler | WARN | Deploy exited 2 on handler; boot loop still running |

**You do (optional):**

1. Unlock p7a; confirm AutoJs6 accessibility service is bound.
2. Re-run `./mac/deploy-fleet.sh p7a` if you want a clean handler pass, or
   `make verify HOSTS=p7a` after a few minutes.

Or tell the agent it may retry deploy when you're not busy (note window in
`RESPONSES.md`).

### 3.2 Production deploy go/no-go

Ansible collections are tagged **v1.4.0**; fleet dry-run on **s24** passed.
Before live `./mac/deploy-fleet.sh` on all hosts:

- Confirm you're OK with Termux sshd restart if `termux_sshd` config changes.
- Confirm Obtainium catalog import (unlocked screen) is acceptable post-deploy.

Answer in `RESPONSES.md`: `deploy_fleet: approved | hold | s24-only | p7a-only`

---

## Priority 4 — Optional / later

### 4.1 Ansible Galaxy publish

Requires [galaxy.ansible.com](https://galaxy.ansible.com) API token. Not needed
for Git-tag installs (`version: stayturgid.termux-1.4.0` in `requirements.yml`).

If you want Galaxy: create token, run locally:

```bash
ansible-galaxy collection build ansible_collections/stayturgid/termux
ansible-galaxy collection publish stayturgid-termux-1.4.0.tar.gz --api-key ...
```

Repeat per collection. Note in `RESPONSES.md` if published.

### 4.2 Neo Store repo import still failing

If `fdroid_repo_push` intents fail after automation (rare activity renames or no
handler): capture `adb logcat` snippet and which client (Neo/Droid-ify/F-Droid)
is installed. Agent may explore content-provider / DB import — needs your device
observation in `RESPONSES.md`.

### 4.3 Obtainium in-app confirm

Catalog apply still uses Mac `obtainium/mac/import_catalog.py` (screen control).
No stable Obtainium API — human must unlock phone when deploy runs import.

---

## Quick reference — env files (never commit)

| Purpose | Suggested path |
|---------|----------------|
| Play apkeep | `~/.config/stayturgid/play.env` |
| gplaycli | `~/.config/gplaycli/gplaycli.conf` |
| ADB aliases | `~/.config/stayturgid/devices.conf` (rendered by `ansible/playbooks/mac.yml`) |

---

## When you're done

Copy `RESPONSES.md.example` → `RESPONSES.md`, fill in checkboxes, tell the agent:

> Read human/RESPONSES.md and continue.
