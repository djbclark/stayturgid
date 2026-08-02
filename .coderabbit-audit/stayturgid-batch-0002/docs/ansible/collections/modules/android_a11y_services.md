# android_a11y_services

**FQCN:** `stayturgid.android_common.android_a11y_services`

Merge-only backup/restore for `enabled_accessibility_services` via adb. Profiles:
`control/lib/a11y_profiles.json`; backups: `control/lib/a11y_backups/<alias>.txt`.

Replaces ad-hoc `control/bin/a11y_services.py` for Ansible-driven flows; CLI kept for
operators.
