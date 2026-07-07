# play_store (Aurora Store / Play)

Ensures Aurora Store (FOSS Google Play client) with Shizuku + optional app sideload.

## Prerequisites

- Aurora Store in Obtainium catalog and/or `stayturgid_install_aurora_store: true`
- Fleet deploy runs `configure_aurora.py` for first-run UI (Shizuku installer, auto-updates)
- Mac: `apkeep` for APK downloads

## Deploy

```bash
./mac/deploy-fleet.sh s24     # full fleet (recommended)
./mac/deploy-play.sh s24      # play tag only
```

See [HANDOFF.md](../../../../HANDOFF.md) for fleet status and [play/README.md](../../../../play/README.md).
