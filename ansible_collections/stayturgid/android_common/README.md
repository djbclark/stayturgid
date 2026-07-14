# stayturgid.android_common

Shared helpers for stayturgid Android automation collections. Usually installed
as a dependency of `stayturgid.termux`, `stayturgid.fdroid`, or `stayturgid.play`.

## Contents

| Type           | Name                     | Purpose                                              |
| -------------- | ------------------------ | ---------------------------------------------------- |
| `module_utils` | `adb_resolve.py`         | Fleet alias → ADB serial (`devices.conf`, USB-first) |
| `module_utils` | `adb_shell.py`           | adb shell helpers for appops/settings modules        |
| `lookup`       | `adb_device`             | Resolve `target_device` in playbooks/roles           |
| `lookup`       | `android_packages`       | `pm list packages` with optional regex               |
| `lookup`       | `fdroid_client`          | Preferred fdroidrepos activity component             |
| `module`       | `android_appops`         | Idempotent `cmd appops` + `pm grant`                 |
| `module`       | `android_a11y_services`  | Merge-only a11y list backup/restore                  |
| `module`       | `autojs6_project_deploy` | AutoJs6 project tree adb push (Fire OS)              |
| `module`       | `android_ui`             | Named screen-control tasks (ADR 002)                 |
| `module`       | `android_settings`       | Idempotent `settings put` (secure/global/system)     |
| `module`       | `shizuku_grant`          | Shizuku API + shizuku.json authorization             |
| `module`       | `android_intent`         | Structured `am start` with implicit fallback         |
| `role`         | `ensure_apps`            | Unified play/fdroid/apk/obtainium dispatch           |
| `role`         | `tailscale_vpn`          | Always-on VPN via `android_settings`                 |

## `devices.conf`

Control-node file (default `~/.config/stayturgid/devices.conf`):

```
# alias usb_serial tailscale_ip lan_ip
p7a 35261JEHN12374 100.65.230.108 192.168.68.65
```

Override path with env `STAYTURGID_DEVICES_CONF`.

See [docs/adoption.md](../docs/adoption.md) for install and consumption patterns.
