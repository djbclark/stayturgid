# Obtainium — GitHub APK auto-updates for stayturgid

Every app installed from **GitHub releases** (not Play Store) should be tracked in [Obtainium](https://github.com/ImranR98/Obtainium) so updates are automatic.

## Catalog files

| File | Contents |
|------|----------|
| `stayturgid-apps.json` | Full fleet catalog (Termux github-debug set, Shizuku, Tailscale, AutoJs6) |
| `autojs6-only.json` | Just AutoJs6 — use after `setup-autojs6.sh` |

APK filters are pre-configured:

- **Termux main:** `github-debug.*arm64-v8a`
- **Termux addons:** `github.debug` (universal APKs)
- **AutoJs6:** `arm64-v8a` (+ `autoApkFilterByArch`)
- **Shizuku (thedjchi):** `thedjchi`
- **Tailscale:** `universal`

## Sync to a device (from Mac)

```bash
chmod +x obtainium/mac/sync-to-device.sh

# After installing AutoJs6 only:
./obtainium/mac/sync-to-device.sh p7a autojs6

# Full catalog (new device or audit):
./obtainium/mac/sync-to-device.sh p7a all
```

On the phone: confirm **Obtainium Import** when prompted (or manually: Obtainium → Import/Export → Obtainium Import → `Download/stayturgid-obtainium-*.json`).

Re-importing updates existing entries; it does not remove other Obtainium apps.

## Apply pending updates (from Mac)

```bash
chmod +x obtainium/mac/apply-updates.sh
./obtainium/mac/apply-updates.sh s24   # phone unlocked
```

Enable **Use Shizuku/Dhizuku/Sui to install** in Obtainium settings for fewer dialogs. GitHub-debug Termux addons may need Play Protect verifier disabled during install (`HACKING.md`). AutoJs6 can show an update badge at the latest tag when the installed APK hash differs — reinstalling the current release clears it.

## Manual add (one app)

In Obtainium → Add App, paste the GitHub URL:

| App | URL |
|-----|-----|
| AutoJs6 | `https://github.com/SuperMonster003/AutoJs6` |
| Shizuku (thedjchi) | `https://github.com/thedjchi/Shizuku` |
| Tailscale | `https://github.com/tailscale/tailscale-android` |
| Termux | `https://github.com/termux/termux-app` |
| Termux:API | `https://github.com/termux/termux-api` |
| Termux:Boot | `https://github.com/termux/termux-boot` |
| Termux:Tasker | `https://github.com/termux/termux-tasker` |
| Termux:Styling | `https://github.com/termux/termux-styling` |
| Termux:Widget | `https://github.com/termux/termux-widget` |
| Termux:Float | `https://github.com/termux/termux-float` |

Deep link (opens Add App with URL pre-filled):

```
obtainium://add/https://github.com/SuperMonster003/AutoJs6
```

Clickable redirect: http://apps.obtainium.imranr.dev/redirect.html?r=obtainium://add/https://github.com/SuperMonster003/AutoJs6

## Policy

- **Play Store apps** (Tasker, AutoInput) — stay on Play; no Obtainium.
- **GitHub / sideload APKs** — always add to Obtainium before considering install done.
- `autojs6/mac/setup-autojs6.sh` runs `sync-to-device.sh p7a autojs6` automatically after install.
