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
| `role`         | `device_quirks`          | Per-model adb settings: get, expect, set, read back           |
| `role`         | `ensure_apps`            | play/apk dispatch                                             |
| `role`         | `tailscale_vpn`          | Always-on VPN via `android_settings`                          |

## Rolling releases

Since 2026-11-21 the fleet follows the newest release instead of pinning one (operator decision: no
pins, breakage accepted). The agent (`org.stayturgid.agent`), Termux and its add-ons (`com.termux`,
`.boot`, `.api`, `.tasker`, `.x11`) and the ShizukuTendCF fork (`moe.shizuku.privileged.api`) use
`gh_latest`; only `com.tailscale.ipn` stays pinned, because replacing it cuts the adb transport. The
installed app is compared by the SHA-256 of its `base.apk` against the asset digest GitHub publishes
(termux-app and termux-boot publish none, so they install unverified with a warning).

Two `android_apk` options choose the release stream, both only with `gh_latest`:

- `gh_tag_prefix`: consider only releases whose tag starts with it, e.g. `agent-r` for
  `djbclark/stayturgid`, which also has `agent-ci-*` and `agent-v*` tags.
- `gh_skip_prereleases` (default false): skip releases GitHub marks as prereleases (used for Termux and
  Shizuku betas); leave it off for an upstream whose only channel is a republished prerelease.

Both are part of the key of the remembered release, so `gh_latest_pin_to_cache` below finds the right
one; with either set, the module lists 100 releases instead of 10.

A rolling release is only as trustworthy as whoever can create one, so pin the signer instead of the
version: `signer_sha256` is the hex SHA-256 of the one signing certificate the APK may carry. The module
runs `apksigner verify --print-certs` and `aapt2 dump badging` on the download (both from the SDK
build-tools directory of `apksigner_bin`, fails closed if missing) and refuses a foreign signer or a
different package before installing or uninstalling anything, on a fresh install too. The role passes
`clean_on_incompatible: false` for every `gh_latest` entry, so a signature mismatch is never answered
by uninstalling the app (set it on the entry to opt back in). The agent entry pins the fleet's release
certificate (`35bbc3d1...`).

## Pin to what the fleet has

`stayturgid_bootstrap_apks_pin_to_fleet=true` (module option `android_apk` `gh_latest_pin_to_cache`)
installs the `gh_latest` release the fleet already runs from `~/.cache/stayturgid/apks` without asking
GitHub, e.g. `just deploy ... -e stayturgid_bootstrap_apks_pin_to_fleet=true`. It fails, and never falls
back to the newest release, when nothing was remembered or the cached APK is missing or differs.

## `devices.conf`

Control-node file (default `~/.config/stayturgid/devices.conf`):

```
# alias usb_serial tailscale_ip lan_ip
stock-android-device EXAMPLE-SERIAL-STOCK 100.0.0.12 192.0.2.65
```

Override path with env `STAYTURGID_DEVICES_CONF`.

See [docs/adoption.md](../../../docs/ansible/collections/adoption.md) for install and consumption patterns.
