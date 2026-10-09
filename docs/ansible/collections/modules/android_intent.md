# android_intent

FQCN: `stayturgid.android_common.android_intent`

Fire an Android intent via `adb shell am start` with structured parameters.
When `component` is set and the explicit start fails (activity renamed across
app versions), optionally falls back to an implicit intent.

## Parameters

| Parameter           | Description                                                        |
| ------------------- | ------------------------------------------------------------------ |
| `device`            | ADB serial or `host:5555` (required)                               |
| `connect`           | Run `adb connect` first (default `true`)                           |
| `action`            | Intent action (default `android.intent.action.VIEW`)               |
| `data`              | Intent data URI (`fdroidrepos://…`, `market://…`, …)               |
| `mime_type`         | MIME type (`-t`)                                                   |
| `component`         | Explicit component (`-n pkg/Activity`)                             |
| `fallback_implicit` | Retry without component when explicit start fails (default `true`) |
| `extras`            | String extras (`--es key value`) as a dict                         |

## Example

```yaml
# As used by the fleet.shizuku_config role
- name: Apply Shizuku fleet profile via intent
  stayturgid.android_common.android_intent:
    device: "{{ adb_target }}"
    action: moe.shizuku.privileged.api.APPLY_FLEET_PROFILE
    component: moe.shizuku.privileged.api/af.shizuku.manager.fleet.FleetProfileActivity
    extras:
      profile_path: /sdcard/Android/data/moe.shizuku.privileged.api/files/shizuku-fleet.json
  delegate_to: localhost
  changed_when: false
```

## Notes

Intents are fire-and-forget; the module reports `changed=true` when an intent
was sent. Use `changed_when` on the task if you treat it as a query.
