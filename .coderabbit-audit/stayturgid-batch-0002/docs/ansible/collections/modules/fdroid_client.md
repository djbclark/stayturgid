# fdroid_client lookup

FQCN: `stayturgid.android_common.fdroid_client`

Returns the preferred `fdroidrepos://` activity component for an adb target.

## Usage

```yaml
_component: "{{ lookup('stayturgid.android_common.fdroid_client', adb_target) }}"

# All installed client components (wantlist)
_components: "{{ query('ansible.builtin.list', lookup('stayturgid.android_common.fdroid_client', adb_target, wantlist=True)) }}"
```

Preference: Neo Store → Droid-ify → F-Droid. Defaults to Neo activity if none installed.

The `fdroid_repo_push` module uses the same preference order internally with fallback.
