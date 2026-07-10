# android_a11y_services

**FQCN:** `stayturgid.android_common.android_a11y_services`

Merge-only backup/restore for `enabled_accessibility_services` via adb. Profiles:
`shared/a11y_profiles.json`; backups: `shared/a11y_backups/<alias>.txt`.

Replaces ad-hoc `mac/a11y_services.py` for Ansible-driven flows; CLI kept for
operators.
