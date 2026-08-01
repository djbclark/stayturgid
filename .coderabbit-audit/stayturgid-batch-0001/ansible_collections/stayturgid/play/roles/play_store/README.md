# play_store (Play)

Ensures optional app sideload via Play backend.

## Prerequisites

- Mac: `apkeep` for APK downloads
- Mac: `apkeep` for APK downloads

## Deploy

```bash
just deploy HOSTS=oneui-device     # full fleet (when app stores enabled)
just deploy SCOPE=play HOSTS=oneui-device
```

See [docs/handoff.md](../../../../../docs/handoff.md) for fleet status and [docs/architecture/components/play.md](../../../../../docs/architecture/components/play.md).
