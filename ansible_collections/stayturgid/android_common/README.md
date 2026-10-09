# stayturgid.android_common

Shared helpers for stayturgid Android automation collections. Usually installed
as a dependency of `stayturgid.termux` or `stayturgid.play`.

## Contents

| Type           | Name                     | Purpose                                                       |
| -------------- | ------------------------ | ------------------------------------------------------------- |
| `module_utils` | `adb_resolve.py`         | Fleet alias → ADB serial (`devices.conf`, USB-first)          |
| `module_utils` | `adb_shell.py`           | adb shell helpers for appops/settings modules                 |
| `lookup`       | `adb_device`             | Resolve `target_device` in playbooks/roles                    |
| `lookup`       | `android_packages`       | `pm list packages` with optional regex                        |
| `lookup`       | `fdroid_client`          | Legacy: fdroidrepos activity component (no caller since #119) |
| `module`       | `android_appops`         | Idempotent `cmd appops` + `pm grant`                          |
| `module`       | `android_a11y_services`  | Merge-only a11y list backup/restore                           |
| `module`       | `android_settings`       | Idempotent `settings put` (secure/global/system)              |
| `module`       | `shizuku_grant`          | pm grant + conditional Shizuku server restart                 |
| `module`       | `android_intent`         | Structured `am start` with implicit fallback                  |
| `module`       | `android_apk`            | adb APK install                                               |
| `module`       | `android_app_privileges` | adb privilege grants (`app_privileges` role)                  |
| `module`       | `native_agent_config`    | Native-agent peer configuration over ADB                      |
| `module`       | `shizuku_start`          | Start Shizuku over ADB and apply the fleet profile            |
| `role`         | `bootstrap_apks`         | Release-locked, checksummed bootstrap APK install over ADB    |
| `role`         | `app_privileges`         | Battery, unused-app and runtime grants for fleet apps         |
| `role`         | `ensure_apps`            | play/apk dispatch                                             |
| `role`         | `tailscale_vpn`          | Always-on VPN via `android_settings`                          |

## `devices.conf`

Control-node file (default `~/.config/stayturgid/devices.conf`):

```
# alias usb_serial tailscale_ip lan_ip
stock-android-device EXAMPLE-SERIAL-STOCK 100.0.0.12 192.0.2.65
```

Override path with env `STAYTURGID_DEVICES_CONF`.

See [docs/adoption.md](../../../docs/ansible/collections/adoption.md) for install and consumption patterns.
