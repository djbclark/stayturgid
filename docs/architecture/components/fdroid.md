# F-Droid / Neo Store — **parked** by default

**Collection:** `stayturgid.fdroid`  
**Role:** `stayturgid.fdroid.fdroid_repos`  
**Playbook:** `ansible/playbooks/fleet/fdroid.yml` (or `just deploy` with app stores enabled)  
**Mac tool:** `control/tools/fdroid/grant_neo_store_shizuku.py`

## Status

Neo Store / F-Droid **are not** part of the default fleet deploy
(`stayturgid_app_stores_enabled: false` in inventory group_vars). Core stack is
Termux + AutoJs6 + Obtainium + Tailscale.

## Re-enable

1. Set in inventory (group or host vars):

   ```yaml
   stayturgid_app_stores_enabled: true
   ```

2. Optional Obtainium entries: `catalogs/obtainium/app-stores-optional.json`.
3. Control node: `brew install fdroidcl` (also in Mac prereqs when app-stores brew set is installed).
4. Deploy:

   ```bash
   just --set scope fdroid --set hosts s24 deploy
   # or:
   ./control/bin/deploy_fleet.py --scope fdroid s24
   ```

## What it does when enabled

| Piece           | Role                                                   |
| --------------- | ------------------------------------------------------ |
| `fdroid_repos`  | Configure `fdroidcl` repos on the Mac / push to device |
| `fdroid_apps`   | Install selected packages                              |
| Neo Store grant | Shizuku installer permission for Neo Store             |

## Related

- [ansible_collections/modules/fdroid_repos.md](../ansible/collections/modules/fdroid_repos.md)
- [play.md](play.md) — Aurora / Play (also parked)
- [obtainium.md](obtainium.md) — preferred APK update path
