# play_apps

**FQCN:** `stayturgid.play.play_apps`  
**Runs on:** control node (`delegate_to: localhost`)

Download APKs via `apkeep` or `gplaycli`, install with `adb`. Optional Play Store
installer spoof (`-i com.android.vending`).

## Prerequisites

- `apkeep` and/or `play/mac/gplaycli.sh` on control node
- Google credentials in env (`GPLAY_EMAIL`, `GPLAY_AAS_TOKEN`, …) for Play downloads
- `adb` + optional `devices.conf`

## Example

```yaml
- stayturgid.play.play_apps:
    apps:
      - id: com.aurora.store
    device: "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"
    download_backend: apkeep
    repo_root: "{{ playbook_dir }}/../.."
  delegate_to: localhost
```

## Role

`stayturgid.play.play_store` role — playbook `ansible/playbooks/play_store.yml`
