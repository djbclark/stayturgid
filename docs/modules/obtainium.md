# Obtainium catalogs — GitHub APK updates

**Repo data:** `catalogs/obtainium/`  
**On device:** Obtainium app + imported JSON catalogs  
**Ansible:** `stayturgid.obtainium` collection (`obtainium_apps` role, `obtainium_app` module)  
**Mac tools:** `control/tools/obtainium/`

## What this module does

| Piece | Role |
|-------|------|
| `catalogs/obtainium/stayturgid-apps.json` | Core fleet catalog (Termux, AutoJs6, Shizuku, …) |
| `catalogs/obtainium/autojs6-only.json` | Minimal catalog |
| `catalogs/obtainium/app-stores-optional.json` | Neo Store / Aurora (parked from default fleet) |
| `control/tools/obtainium/import_catalog.py` | Deep-link / UI import of a catalog JSON |
| `control/tools/obtainium/sync_to_device.py` | Push catalog files to the phone |
| `control/tools/obtainium/apply_updates.py` | Drive Obtainium update / installer dialogs |
| `control/tools/obtainium/enable_shizuku_installer.py` | Grant Shizuku installer to Obtainium |

## Standalone use

Any Obtainium user can import a JSON catalog without the rest of stayturgid:

1. Install Obtainium (GitHub release preferred).
2. Copy a file from `catalogs/obtainium/` to the device.
3. Obtainium → Import → select the JSON (or use the deep-link import script).

## Fleet deploy

Included in `make deploy` / `ansible/playbooks/site.yml` via `stayturgid.obtainium.obtainium_apps`.

Post-UI import (screen control) prefers SSH → Termux `localhost:5555` on s24/p7a; hd8 uses Mac adb (no Termux loopback).

```bash
make deploy HOSTS=s24
# catalog-only helpers:
python3 control/tools/obtainium/sync_to_device.py s24
python3 control/tools/obtainium/import_catalog.py s24
```

## Related

- [docs/hacking.md](../hacking.md) — Obtainium setup notes  
- [ansible_collections/docs/modules/obtainium_app.md](../../ansible_collections/docs/modules/obtainium_app.md)  
- Parked app stores: [fdroid.md](fdroid.md), [play.md](play.md)  
