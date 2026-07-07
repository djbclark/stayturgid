# fdroid_repos

Ansible role + (future) `stayturgid.fleet.fdroid_repos` module for managing F-Droid repositories on the device and ensuring a working F-Droid GUI client.

## Features (per project)
- Declaratively manage F-Droid repos via `fdroidcl` (control machine; `brew install fdroidcl` or equivalent).
- Role supports `target_device` (p7a/s24/IP:5555/serial) for adb detection and grants.
- Defaults include IzzyOnDroid + support for more.
- **Client guarantee** (review req): Ensure "Neo Store" (via Obtainium catalog) and configure for Shizuku + auto background updates (if already present, still configure).

## Usage

```yaml
- hosts: stayturgid
  roles:
    - role: fdroid_repos
      vars:
        target_device: p7a
        stayturgid_fdroid_repos:
          - name: IzzyOnDroid
            address: https://apt.izzysoft.de/fdroid/repo
          - name: Guardian Project
            address: https://guardianproject.info/fdroid/repo
```

`fdroidcl` must be on control machine ( `brew install fdroidcl` ).

Run after `obtainium_apps` (for Neo Store in catalog).

The role:
- Ensures repos in local fdroidcl (for `fdroidcl install <id>` from Mac).
- Pushes repos to on-device Neo Store via explicit intent (bypasses chooser using preference Neo > Droid-ify > F-Droid).
- Ensures Neo Store + Shizuku grant + note for auto-updates.

After: use `fdroidcl install <pkg>` to push apps from the repos to device.

See top-level `fdroid/` docs and `HANDOFF.md` (fdroid_repos section) for status + next actions.

## Client configuration notes
- Shizuku permission: granted via existing stayturgid Shizuku grant flows / shizuku.json patching (see `shared/mac/stayturgid_device.py` and obtainium grant script).
- In Neo Store: enable "Use Shizuku/Dhizuku/Sui to install" and background/auto updates.
- First app installed *through* Neo Store will then auto-update in background.

See top-level `fdroid/` docs and the main HANDOFF for overall context.
