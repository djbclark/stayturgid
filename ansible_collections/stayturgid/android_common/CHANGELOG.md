# Changelog — stayturgid.android_common

## Unreleased (galaxy.yml still says 1.5.0; recorded 2026-10-09 from git history)

- Remove `autojs6_project_deploy` and `autojs6_deploy_util` with the rest of
  AutoJs6 (87bf130, 2026-07-31, #162).
- Add `native_agent_config` module (a9e07ce, 2026-07-26).
- Add `shizuku_start` module and `bootstrap_apks` role (2026-07-13).
- Add `android_app_privileges` module and `app_privileges` role (d3b285d,
  2026-07-08). Not listed in the 1.4.x / 1.5.0 entries below.

## 1.5.0 (2026-07-09)

- Add `autojs6_project_deploy` module + `autojs6_deploy_util` (Fire OS adb path;
  shared with `control/tools/autojs6/deploy.py`).

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
