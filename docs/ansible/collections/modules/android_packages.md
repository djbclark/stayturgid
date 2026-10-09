# android_packages lookup

FQCN: `stayturgid.android_common.android_packages`

List installed packages on an adb target (control node).

## Usage

```yaml
# All packages
_all: "{{ lookup('stayturgid.android_common.android_packages', adb_target) }}"

# Regex filter (second term)
_termux: "{{ lookup('stayturgid.android_common.android_packages', adb_target, 'termux') }}"

# Membership test
_has_agent: "{{ 'org.stayturgid.agent' in lookup('stayturgid.android_common.android_packages', adb_target) }}"
```

Replaces shell `pm list packages` tasks in roles (for example `fleet.validate`).
