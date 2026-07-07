# F-Droid / Neo Store support

Ansible role `stayturgid.fdroid.fdroid_repos` plus Mac `fdroidcl` for repo management and app installs.

## Fleet integration

F-Droid is part of the standard fleet deploy (`./mac/deploy_fleet.py`):

1. Core Ansible run (includes fdroid role — syncs repos on Mac)
2. Obtainium catalog import (installs Neo Store on device)
3. App-stores re-run (pushes repos to Neo Store, grants Shizuku)

Re-run F-Droid only: `./mac/deploy_fleet.py --scope fdroid [host]`

## Prerequisites

- Neo Store in Obtainium catalog (installed by fleet deploy)
- Mac: `brew install fdroidcl`
- Shizuku privileged shell on device

## Quick start

```bash
./mac/deploy_fleet.py s24          # full stack (recommended)
./mac/deploy_fleet.py --scope fdroid s24         # F-Droid roles only
ANDROID_SERIAL=s24 fdroidcl install org.breezyweather
```

## What the role does

- Ensures repos in `fdroidcl` on the Mac (IzzyOnDroid, Guardian Project by default)
- Pushes repos to on-device client via `fdroid_repo_push` (Neo → Droid-ify → F-Droid)
- Grants Shizuku to Neo Store via `stayturgid.android_common.shizuku_grant`

**Human step:** In Neo Store → Settings → Installer → Shizuku, enable automatic updates.

## Key files

- `ansible/playbooks/fleet.yml` — includes `fdroid_repos` role
- `ansible_collections/stayturgid/fdroid/` — collection modules + role
- `fdroid/mac/grant_neo_store_shizuku.py` — removed stub (use `shizuku_grant` module)

See [HANDOFF.md](../HANDOFF.md) for fleet status and [HACKING.md](../HACKING.md) Part 6b for repo fingerprints.
