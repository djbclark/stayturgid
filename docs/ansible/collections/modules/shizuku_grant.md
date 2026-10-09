# shizuku_grant

FQCN: `stayturgid.android_common.shizuku_grant`

Grant Shizuku API access to an app (for example `org.stayturgid.agent` or
`com.termux`) via the privileged adb shell. The module runs `pm grant` for
`moe.shizuku.manager.permission.API_V23`, then restarts the Shizuku server
only if one is already running, so the grant takes effect at once. It no
longer reads or writes Shizuku's `shizuku.json` file.

## Parameters

| Parameter | Description                                     |
| --------- | ----------------------------------------------- |
| `device`  | ADB serial or `host:5555` with privileged shell |
| `package` | App package to authorize                        |
| `connect` | Run `adb connect` first (default `true`)        |

The module accepts no other parameters; the former `shizuku_json` and
`staging_path` options were removed, and Ansible rejects them.

## Example

```yaml
- stayturgid.android_common.shizuku_grant:
    device: "{{ adb_target }}"
    package: org.stayturgid.agent
  delegate_to: localhost
```

## Role usage

`stayturgid.android_common.bootstrap_apks` calls this module for each locked
APK whose entry sets `shizuku_grant: true` (`tasks/install_apk.yml`).
