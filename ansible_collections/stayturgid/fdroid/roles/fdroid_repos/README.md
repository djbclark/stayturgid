# fdroid_repos

Ansible role + `stayturgid.fdroid.fdroid_repos` module for F-Droid repository management.

## Scope

| Layer | Tool | What it does |
|-------|------|--------------|
| Control machine | `fdroidcl` | Add/enable repos; `fdroidcl install <id>` |
| App ensure | `stayturgid.fdroid.fdroid_apps` | `stayturgid_fdroid_apps` list → fdroidcl install |
| On-device | Neo Store (via Obtainium) | GUI client; repos pushed via `fdroidrepos://` intent |
| Shizuku | `stayturgid.android_common.shizuku_grant` | Patches `shizuku.json` via privileged shell |

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

Set `stayturgid_fdroid_apps` to install apps from the control node (symmetric to
`stayturgid_play_apps`):

```yaml
stayturgid_fdroid_apps:
  - id: org.breezyweather
```

After the role: install through Neo Store on device, or rely on `fdroid_apps` /
`fdroidcl install <appid>` from the Mac.

## Client setup (manual on device)

After Shizuku grant: Neo Store → Settings → Shizuku installer + automatic updates.
