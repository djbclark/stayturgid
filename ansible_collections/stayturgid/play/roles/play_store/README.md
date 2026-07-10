# play_store (Aurora Store / Play)

Ensures Aurora Store (FOSS Google Play client) with Shizuku + optional app sideload.

## Prerequisites

- Aurora Store in Obtainium catalog and/or `stayturgid_install_aurora_store: true`
- Fleet deploy runs `stayturgid.fleet.post_ui` / `android_ui` task `configure_aurora`
  for first-run UI when `stayturgid_app_stores_enabled: true`
- Mac: `apkeep` for APK downloads

## Deploy

```bash
make deploy HOSTS=s24     # full fleet (when app stores enabled)
make deploy SCOPE=play HOSTS=s24
```

See [HANDOFF.md](../../../../HANDOFF.md) for fleet status and [play/README.md](../../../../play/README.md).
