# android_settings

FQCN: `stayturgid.android_common.android_settings`

Idempotent `settings put` over adb for `secure`, `global`, or `system` namespaces.

## Parameters

| Parameter         | Description                                    |
| ----------------- | ---------------------------------------------- |
| `device`          | ADB serial or `host:5555`                      |
| `connect`         | Run `adb connect` first (default `true`)       |
| `settings`        | List of `{namespace, key, value}` (required)   |
| `require_package` | Skip all changes when package is not installed |

## Example

```yaml
- stayturgid.android_common.android_settings:
    device: "{{ adb_target }}"
    require_package: com.tailscale.ipn
    settings:
      - namespace: secure
        key: always_on_vpn_app
        value: com.tailscale.ipn
      - namespace: secure
        key: always_on_vpn_lockdown
        value: "1"
  delegate_to: localhost
```

## Role usage

`stayturgid.android_common.tailscale_vpn` uses this module for always-on VPN.
