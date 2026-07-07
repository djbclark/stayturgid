# Play Store (Aurora + apkeep / gplaycli)

Aurora Store is the on-device GUI client. Fleet deploy installs Aurora when missing, grants Shizuku, completes first-run setup, selects the Shizuku installer, and enables automatic installs. App automation downloads APKs on the Mac and installs via adb, spoofing Play as installer when requested.

## Fleet integration

Play/Aurora is part of `./mac/deploy-fleet.sh` (play role + `configure_aurora.py` after Obtainium import).

Re-run Play only: `./mac/deploy-play.sh [host]`

## Components

| Piece | Deploy path | Role |
|-------|-------------|------|
| **Aurora Store** | `stayturgid_install_aurora_store: true` in fleet group_vars | GUI updates; Shizuku installer |
| **play_apps module** | `stayturgid_play_apps` in role vars | apkeep/gplaycli + adb install |
| **configure_aurora.py** | end of `deploy-fleet.sh` / `deploy-play.sh` | First-run UI automation |

```bash
./mac/deploy-fleet.sh s24    # full stack (recommended)
./mac/deploy-play.sh s24     # Play roles + Aurora UI setup only
```

## Play downloads

Set `GPLAY_*` env or `gplaycli.conf` for `google-play` source; apk-pure mirrors work without login but are flaky. See [play/README credentials section](README.md) if documented, or [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md).

## Collection

`stayturgid.play` — role `play_store`, module `play_apps`. See [ansible_collections/stayturgid/play/README.md](../ansible_collections/stayturgid/play/README.md).
