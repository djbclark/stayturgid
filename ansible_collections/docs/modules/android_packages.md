# android_packages lookup

FQCN: `stayturgid.android_common.android_packages`

List installed packages on an adb target (control node).

## Usage

```yaml
# All packages
_all: "{{ lookup('stayturgid.android_common.android_packages', adb_target) }}"

# Regex filter (second term)
_fdroid: "{{ lookup('stayturgid.android_common.android_packages', adb_target, 'fdroid|droidify') }}"

# Membership test
_has_neo: "{{ neo_store_package in lookup('stayturgid.android_common.android_packages', adb_target) }}"
```

Replaces shell `pm list packages` tasks in fdroid and play roles.
