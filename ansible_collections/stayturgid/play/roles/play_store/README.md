# play_store (Play)

Ensures optional app sideload via Play backend.

## Prerequisites

- Mac: `apkeep` for APK downloads
- Mac: `apkeep` for APK downloads

## Deploy

```bash
just deploy oneui-device              # full deploy of one host (when app stores enabled)
scope=play just deploy oneui-device   # Play scope only
```

See [docs/handoff.md](../../../../../docs/handoff.md) for fleet status and [docs/architecture/components/play.md](../../../../../docs/architecture/components/play.md).
