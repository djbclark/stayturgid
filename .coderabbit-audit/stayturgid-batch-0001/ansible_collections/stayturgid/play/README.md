# stayturgid.play

Google Play APK download and sideload (apkeep/gplaycli + adb). Integrated in `ansible/playbooks/fleet/fleet.yml`.

- **Module:** `stayturgid.play.play_apps`
- **Role:** `stayturgid.play.play_store`
- **Docs:** [play_apps.md](../../../docs/ansible/collections/modules/play_apps.md)

Depends on `stayturgid.android_common` for the `adb_device` lookup.
