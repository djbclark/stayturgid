# android_appops

FQCN: `stayturgid.android_common.android_appops`

Idempotent Android appops and runtime permission grants over adb.

## Parameters

| Parameter               | Description                                              |
| ----------------------- | -------------------------------------------------------- |
| `device`                | ADB serial or `host:5555`                                |
| `connect`               | Run `adb connect` first (default `true`)                 |
| `appops`                | List of `{package, op, mode}` — mode defaults to `allow` |
| `permissions`           | List of `{package, permission}` for `pm grant`           |
| `skip_missing_packages` | Skip when package not installed (default `true`)         |

## Example

```yaml
- stayturgid.android_common.android_appops:
    device: localhost:5555
    appops:
      - package: com.termux.api
        op: WRITE_SETTINGS
        mode: allow
    permissions:
      - package: com.termux
        permission: android.permission.POST_NOTIFICATIONS
```

## Role usage

`stayturgid.termux.termux_userland` calls this module for Termux:API WRITE_SETTINGS,
overlay ops, and POST_NOTIFICATIONS on the privileged shell (`localhost:5555`).
