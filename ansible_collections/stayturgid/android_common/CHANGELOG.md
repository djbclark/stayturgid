# Changelog — stayturgid.android_common

## Unreleased (galaxy.yml still says 1.5.0; recorded 2026-10-09 from git history)

- Add `device_quirks` role (2026-11-20): reads each `stayturgid_device_quirks` item over adb,
  applies only the ones that differ, reads them back and fails on a mismatch; healing ID
  `DEVICE-QUIRKS`. First data: `model_idea_tab_11` (rotation lock, ZUI memory cleaner, Doze
  whitelist, phantom-process limits).
- `android_apk` `gh_latest`: when GitHub is unreachable, reuse the release last resolved if its
  APK is still in the sha256 cache, else leave an installed app alone (both warn); a first
  install with nothing cached still fails (2026-11-21).
- `android_apk` `gh_latest_pin_to_cache` and role var `stayturgid_bootstrap_apks_pin_to_fleet`
  (both default false): install the remembered fleet release and its cached APK without asking
  GitHub; fail when none is remembered or the cached APK is missing or mismatched (2026-11-21).
- `adb_device` lookup: a host missing from `devices.conf` resolves to its inventory
  `device_usb_serial` (2026-11-20).
- Remove the legacy project-deploy module and its util (87bf130, 2026-07-31, #162).
- Add `native_agent_config` module (a9e07ce, 2026-07-26).
- Add `shizuku_start` module and `bootstrap_apks` role (2026-07-13).
- Add `android_app_privileges` module and `app_privileges` role (d3b285d,
  2026-07-08). Not listed in the 1.4.x / 1.5.0 entries below.

## 1.5.0 (2026-07-09)

- Add the legacy project-deploy module and its util (Fire OS adb path; removed in #162).

## 1.4.1 (2026-07-08)

- `adb_resolve`: parse mDNS wireless-debugging device ids (spaces in serial).

## 1.4.0 (2026-07-07)

- Add `android_packages` and `fdroid_client` lookup plugins.
- Add `ensure_apps` role (unified play/fdroid/apk/obtainium dispatch).
- `android_intent` module (1.3.0).

## 1.3.0 (2026-07-07)

- Add `android_appops`, `android_settings`, `shizuku_grant`, `android_apk` modules.
- Add `tailscale_vpn` role.

## 1.0.0

- Initial `adb_device` lookup and `adb_resolve` module_utils.
