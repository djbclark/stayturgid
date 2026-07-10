# android_app_privileges

FQCN: `stayturgid.android_common.android_app_privileges`

Idempotent fleet app hardening over adb:

- Runtime `pm grant` (explicit list + optional grant-all-ungranted scan)
- `cmd appops` (overlay, storage, background run, auto-revoke-off)
- Doze whitelist when `battery_unrestricted: true` (`dumpsys deviceidle whitelist +<pkg>` + active standby)
- Battery optimization when `battery_unrestricted: false` (remove whitelist, background appops → ignore)

Profiles: `shared/fleet_app_profiles.json` (loaded by role defaults). Mac twin:
`./mac/harden_fleet_apps.py <host>`.
