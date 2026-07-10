# fdroid_repos

**FQCN:** `stayturgid.fdroid.fdroid_repos`  
**Runs on:** control node (`delegate_to: localhost`)

Declarative F-Droid repos in `fdroidcl` config. Pair with `fdroid_repos` role for
on-device `fdroidrepos://` intent push and Shizuku grant.

## Prerequisites

- `brew install fdroidcl` (or fdroidcl on PATH)
- `adb` + optional `devices.conf` (see `stayturgid.android_common`)

## Example

```yaml
- stayturgid.fdroid.fdroid_repos:
    repos:
      - name: IzzyOnDroid
        address: https://apt.izzysoft.de/fdroid/repo
        fingerprint: 3BF0D6ABFEAE2F401707B6D966BE743BF0EEE49C2561B9BA39073711F628937A
    device: "{{ lookup('stayturgid.android_common.adb_device', 'p7a') }}"
  delegate_to: localhost
```

## Role

`stayturgid.fdroid.fdroid_repos` role — playbook `ansible/playbooks/fleet/fdroid.yml`
