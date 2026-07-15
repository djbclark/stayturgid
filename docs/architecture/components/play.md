# Play / Aurora Store — **parked** by default

**Collection:** `stayturgid.play`  
**Role:** `stayturgid.play.play_store`  
**Module:** `stayturgid.play.play_apps`  
**Playbook:** `ansible/playbooks/fleet/play_store.yml`  
**Mac tools:** `control/tools/play/` (`gplaycli.py`, `configure_aurora.py`, …)

## Status

Aurora Store / Play download automation **are not** part of the default fleet
deploy (`stayturgid_app_stores_enabled: false`). Re-enable only when you need
Play-sourced APKs and accept credential / UI blast radius.

## Credentials

Play silent download needs `GPLAY_*` (and usually `GPLAY_EMAIL`) in:

```text
~/.config/stayturgid/play.env
```

See collection docs and human handoff for token acquisition. Do not commit secrets.

## Re-enable

1. Inventory:

   ```yaml
   stayturgid_app_stores_enabled: true
   ```

2. Install Mac tools: `brew install apkeep` (and related prereqs).
3. Configure `play.env`.
4. Deploy:

   ```bash
   just --set scope play --set hosts s24 deploy
   ./control/bin/deploy_fleet.py --scope play s24
   ```

## CLI helper

```bash
python3 control/tools/play/gplaycli.py --help
```

(The old `gplaycli.sh` wrapper was removed; call `gplaycli.py` directly.)

## Fire HD 8 caveat

Sideloaded Google Play on Fire OS can auto-update GMS past compatible builds.
See [docs/research/fire-os-google-play.md](../research/fire-os-google-play.md) and
just fix-hd8-google / just verify-hd8-google.

## Related

- [ansible_collections/modules/play_apps.md](../ansible/collections/modules/play_apps.md)
- [fdroid.md](fdroid.md) — F-Droid / Neo (parked)
- [obtainium.md](obtainium.md) — default update path
