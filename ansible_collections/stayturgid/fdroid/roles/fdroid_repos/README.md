# fdroid_repos

Ansible role + `stayturgid.fdroid.fdroid_repos` module for F-Droid repository management.

## Scope

| Layer | Tool | What it does |
|-------|------|--------------|
| Control machine | `fdroidcl` | Add/enable repos; `fdroidcl install <id>` |
| On-device | Neo Store (via Obtainium) | GUI client; repos pushed via `fdroidrepos://` intent |
| Shizuku | `grant_neo_store_shizuku.py` | Patches `shizuku.json` via privileged shell |

The **module** only manages `fdroidcl` on the Mac. Neo Store install, Shizuku grant, and on-device repo import are **role** tasks.

## Prerequisites

1. `brew install fdroidcl` on the control machine
2. Device reachable via `adb` (`target_device`: fleet alias, serial, or `host:5555`)
3. **Neo Store installed** — run `obtainium_apps` role first; install from catalog on device

## Usage

```yaml
- hosts: stayturgid
  roles:
    - obtainium_apps
    - role: fdroid_repos
      vars:
        target_device: p7a
```

Default repos: IzzyOnDroid + Guardian Project (with fingerprints).

After the role: `fdroidcl install <appid>` from the Mac, or install through Neo Store on device.

## Client setup (manual on device)

After Shizuku grant: Neo Store → Settings → Shizuku installer + automatic updates.
