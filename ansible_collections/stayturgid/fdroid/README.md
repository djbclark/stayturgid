# stayturgid.fdroid

F-Droid repository management via `fdroidcl` on the control node. Integrated in `ansible/playbooks/fleet.yml`.

- **Module:** `stayturgid.fdroid.fdroid_repos`, `stayturgid.fdroid.fdroid_apps`
- **Role:** `stayturgid.fdroid.fdroid_repos`
- **Docs:** [docs/modules/fdroid_repos.md](../../docs/modules/fdroid_repos.md), [fdroid_apps.md](../../docs/modules/fdroid_apps.md)

Depends on `stayturgid.android_common` for the `adb_device` lookup.
