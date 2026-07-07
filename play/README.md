# Play Store side project (Aurora + apkeep / gplaycli)

Aurora Store is the on-device GUI client (Obtainium catalog). Automation downloads APKs on the Mac and installs via adb, spoofing Play as installer when requested.

## Prerequisites

| Tool | Install | Role |
|------|---------|------|
| **Aurora Store** | Obtainium catalog on device | GUI updates; Shizuku installer |
| **apkeep** | `brew install apkeep` | Primary downloader (`apk-pure` or `google-play`) |
| **gplaycli** | `brew install gplaycli` + `play/mac/gplaycli.sh` | Alternate downloader (needs `gplaycli.conf`) |

```bash
./mac/deploy-play.sh p7a    # Shizuku grant to Aurora (once Aurora installed)
```

## Download sources

**apk-pure** (apkeep default): no Google login; mirror availability varies.

**google-play** (apkeep or gplaycli): requires credentials — not stored in git.

```bash
# apkeep (google-play) — email + AAS token from your Play session, or:
export GPLAY_EMAIL='you@gmail.com'
export GPLAY_AAS_TOKEN='...'   # or GPLAY_AUTH_TOKEN for Aurora-style token

# gplaycli — copy play/gplaycli.conf.example → ~/.config/gplaycli/gplaycli.conf
# Set token=False and use a Google App Password.
```

## Ansible

```yaml
- stayturgid.fleet.play_apps:
    device: p7a
    apps:
      - id: com.example.app
    download_source: apkeep
    apkeep_source: apk-pure   # or google-play when creds are set
```

Or with a local APK (no download):

```yaml
- stayturgid.fleet.play_apps:
    device: p7a
    apps:
      - id: com.example.app
        apk_path: /path/to/app.apk
    download_backend: none
```

Install uses `adb install -r -i com.android.vending` by default (`spoof_play_installer: true`).

## Open Aurora to an app page (manual fallback)

```bash
adb -s p7a shell am start -a android.intent.action.VIEW \
  -d 'market://details?id=com.example.app' -n com.aurora.store/.MainActivity
```
