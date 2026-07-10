# fdroid_apps

**FQCN:** `stayturgid.fdroid.fdroid_apps`  
**Runs on:** control node (`delegate_to: localhost`)

Install F-Droid apps via `fdroidcl install` with `ANDROID_SERIAL` set to the adb
target. Idempotent when packages are already on the device.

## Prerequisites

- `brew install fdroidcl` (repos synced — run `fdroid_repos` role or module first)
- `adb` + optional `devices.conf` (see `stayturgid.android_common`)

## Example

```yaml
- stayturgid.fdroid.fdroid_apps:
    apps:
      - id: org.breezyweather
    device: "{{ lookup('stayturgid.android_common.adb_device', 'p7a') }}"
  delegate_to: localhost
```

## Role

`stayturgid.fdroid.fdroid_repos` role — set `stayturgid_fdroid_apps` in role vars
(playbook `ansible/playbooks/fleet.yml` when `stayturgid_app_stores_enabled: true`).
