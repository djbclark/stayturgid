# fdroid_repo_push

FQCN: `stayturgid.fdroid.fdroid_repo_push`

Push F-Droid repository URLs to on-device clients via `fdroidrepos://` intents.

## Behavior

1. Detects installed clients (Neo Store, Droid-ify, F-Droid) in preference order.
2. For each repo with `state: present`, fires VIEW intent with explicit component.
3. On activity-not-found, retries implicit intent (no component).
4. Tries each installed client until one succeeds.
5. Optionally runs `fdroidcl update` to sync the control-node index with the device.

If all intents fail, see [human/HANDOFF-HUMAN.md](../../../../human/HANDOFF-HUMAN.md) §4.2
for operator troubleshooting (content-provider / DB import is not automated).

## Parameters

| Parameter    | Description                                       |
| ------------ | ------------------------------------------------- |
| `device`     | ADB target                                        |
| `repos`      | Same shape as `fdroid_repos` module               |
| `sync_index` | Run `fdroidcl update` after push (default `true`) |

## Example

```yaml
- stayturgid.fdroid.fdroid_repo_push:
    device: "{{ adb_target }}"
    repos: "{{ stayturgid_fdroid_repos }}"
  delegate_to: localhost
  changed_when: false
```
