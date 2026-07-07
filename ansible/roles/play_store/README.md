# play_store (Aurora Store / Play side project)

Ansible role for Google Play via [Aurora Store](https://gitlab.com/AuroraOSS/AuroraStore) (FOSS client), symmetric to `fdroid_repos` / Neo Store.

## Status
- Aurora Store in Obtainium catalog.
- `deploy-play.sh` grants Shizuku via privileged adb (`grant_neo_store_shizuku.py`).
- **p7a verified** (2026-07-07): idempotent Shizuku grant.
- No open “repo” like F-Droid; automation path is gplaycli download + `adb install -i com.android.vending`.

## Usage

```bash
# After Obtainium import (Aurora installed on device):
./mac/deploy-play.sh p7a
```

Or `ansible/playbooks/play_store.yml`. Not part of `./mac/deploy-fleet.sh`.

See HANDOFF.md (“Side project: fdroid_repos / play_store”) for full context.
