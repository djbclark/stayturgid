# Play Store side project (Aurora + apkeep / gplaycli)

Aurora Store is the on-device GUI client. `deploy-play.sh` installs Aurora when missing, grants Shizuku, completes first-run setup, selects the Shizuku installer, and enables automatic installs. App automation downloads APKs on the Mac and installs via adb, spoofing Play as installer when requested.

## Prerequisites

| Tool | Install | Role |
|------|---------|------|
| **Aurora Store** | `./mac/deploy-play.sh` via `apkeep -d f-droid` when missing | GUI updates; Shizuku installer |
| **apkeep** | `brew install apkeep` | Primary downloader (`apk-pure` or `google-play`) |
| **gplaycli** | `brew install gplaycli` + `play/mac/gplaycli.sh` | Alternate downloader (needs `gplaycli.conf`) |

```bash
./mac/deploy-play.sh p7a    # install/configure Aurora + grant Shizuku
```

**Mac firewall:** allow outbound network for `apkeep` and `python` (e.g. Lulu). APKPure may deliver `.xapk` bundles; `play_apps` extracts `base.apk` automatically.

## Download sources

**apk-pure** (apkeep default): no Google login; mirror availability varies. Use `stayturgid_play_apkeep_options: arch=arm64-v8a` for fleet devices.

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

Manual fallback (opens Aurora to each app page):

```bash
./play/mac/open-play-app.sh p7a com.example.app
# or in role: stayturgid_play_open_aurora: true
```
