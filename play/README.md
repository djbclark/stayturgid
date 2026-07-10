# Play Store (Aurora + apkeep / gplaycli)

Aurora Store is the on-device GUI client. Fleet deploy installs Aurora when missing, grants Shizuku, completes first-run setup, selects the Shizuku installer, sets **Do not auto-update** (so Aurora stays battery-optimized without fighting a check&install → unrestrict prompt), and turns on **Filter apps from other sources** (+ F-Droid filter) so Aurora only checks/updates apps it installed. Aurora stays under OS battery optimization (not Doze-whitelisted) to avoid background CPU thrash. App automation downloads APKs on the Mac and installs via adb, spoofing Play as installer when requested.

## Fleet integration

Play/Aurora is part of `./mac/deploy_fleet.py` (play role + `configure_aurora.py` after Obtainium import).

Re-run Play only: `./mac/deploy_fleet.py --scope play [host]`

## Components

| Piece | Deploy path | Role |
|-------|-------------|------|
| **Aurora Store** | `stayturgid_install_aurora_store: true` in fleet group_vars | GUI updates; Shizuku installer |
| **play_apps module** | `stayturgid_play_apps` in role vars | apkeep/gplaycli + adb install |
| **configure_aurora.py** | end of `deploy_fleet.py` / `deploy_fleet.py --scope play` | First-run UI automation |

```bash
./mac/deploy_fleet.py s24    # full stack (recommended)
./mac/deploy_fleet.py --scope play s24     # Play roles + Aurora UI setup only
```

## Play downloads

Set `GPLAY_*` env or `gplaycli.conf` for `google-play` source; apk-pure mirrors work without login but are flaky.

**Recommended (apkeep AAS):** run the Mac helper — it opens Google EmbeddedSetup,
waits for the `oauth_token` cookie after you click **I agree** (the page spinner
never finishes; that is normal), then exchanges it for a long-lived AAS token:

```bash
~/.venv-stayturgid-play/bin/python play/mac/obtain_play_aas.py -e you@gmail.com --smoke-test
# first time: python3 -m venv ~/.venv-stayturgid-play && ~/.venv-stayturgid-play/bin/pip install browser-cookie3
source ~/.config/stayturgid/play.env
```

**Alternate (gplaycli):** App Password in `~/.config/gplaycli/gplaycli.conf` —
often gets `BadAuthentication` from Google now; prefer apkeep.

See [human/HANDOFF-HUMAN.md](../human/HANDOFF-HUMAN.md) §1.1.

## Collection

`stayturgid.play` — role `play_store`, module `play_apps`. See [ansible_collections/stayturgid/play/README.md](../ansible_collections/stayturgid/play/README.md).
