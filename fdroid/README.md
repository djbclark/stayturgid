# F-Droid / Neo Store support (fdroid_repos side project)

This complements the Obtainium/GitHub path with first-class support for F-Droid repositories and the recommended GUI client (Neo Store).

## What was added / status
- fdroidcl installed on Mac via `brew install fdroidcl` (v0.8.1).
- Neo Store (`com.machiav3lli.fdroid`) entry in the Obtainium catalog.
- New role `ansible/roles/fdroid_repos` + module `.../fdroid_repos.py` (uses fdroidcl for repo management in local fdroidcl config; device detection for Neo Store).
- Role supports `target_device` (alias/IP/serial), defaults to ensuring IzzyOnDroid + other F-Droid repos.
- Grant helper `fdroid/mac/grant_neo_store_shizuku.py` for Shizuku auth (reuses project shared code).
- Per review requirement: ensures/configures Neo Store for Shizuku + background updates.
- Tested defensively on p7a and s24 (role runs, grants, fdroidcl downloads + targeted adb installs/uninstalls of small apps from managed repos). All cleaned up with announcements.
- fdroidcl repo management is desktop-side (for installs via fdroidcl); on-device Neo Store GUI is set up separately via grant + user/app settings for auto-updates.

## How to use
In your fleet or a play (after obtainium_apps role):

```yaml
- hosts: stayturgid
  roles:
    - fdroid_repos
  vars:
    target_device: p7a
    stayturgid_fdroid_repos:
      - name: IzzyOnDroid
        address: https://apt.izzysoft.de/fdroid/repo
      - name: Guardian Project
        address: https://guardianproject.info/fdroid/repo
```

`fdroidcl` on control machine.

The role ensures repos in fdroidcl (use `fdroidcl install <id>` to push to device) and to on-device Neo Store (via explicit intent, no chooser).

See role README for details.

## Client setup (Shizuku + background updates) — per review requirement
- If no GUI F-Droid client: install "Neo Store" (via Obtainium catalog we added) + configure.
- If already installed: still configure Shizuku (if not) and background auto-updates (if not).
- Use the helper: `fdroid/mac/grant_neo_store_shizuku.py <p7a|s24|...>` (reuses shared shizuku.json patch, idempotent).
- Then in the Neo Store app (on device):
  - Settings → Installer → select Shizuku / Dhizuku / Sui.
  - Enable automatic background updates.
- After installing at least one app *through* Neo Store, it gains background update capability for those apps.

The `fdroid_repos` Ansible role calls the grant helper automatically when `stayturgid_ensure_neo_store: true`.

See the role README for details.

See `HANDOFF.md` (search for "Side project: fdroid_repos") for full status, next actions, and handoff notes.

This is a side project and does not affect the main device onboarding work.
