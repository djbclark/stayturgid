# android_app_privileges

FQCN: `stayturgid.android_common.android_app_privileges`

Idempotent fleet app hardening over adb:

- Runtime `pm grant` (explicit list + optional grant-all-ungranted scan)
- `cmd appops` (overlay, storage, background run, auto-revoke-off)
- Doze whitelist (`dumpsys deviceidle whitelist +<pkg>`)
- Active standby bucket (`am set-standby-bucket <pkg> active`)

Profiles live in `roles/app_privileges/defaults/main.yml`. Mac twin:
`./mac/harden_fleet_apps.py <host>`.
