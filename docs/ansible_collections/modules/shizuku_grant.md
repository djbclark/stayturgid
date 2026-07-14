# shizuku_grant

FQCN: `stayturgid.android_common.shizuku_grant`

Grant Shizuku API access to an app (Neo Store, Aurora Store, etc.) via the
privileged adb shell.

## Parameters

| Parameter      | Description                                                                |
| -------------- | -------------------------------------------------------------------------- |
| `device`       | ADB serial or `host:5555` with privileged shell                            |
| `package`      | App package to authorize                                                   |
| `connect`      | Run `adb connect` first (default `true`)                                   |
| `shizuku_json` | Path to Shizuku auth file (default `/data/local/tmp/shizuku/shizuku.json`) |
| `staging_path` | Staging path for adb push                                                  |

## Example

```yaml
- stayturgid.android_common.shizuku_grant:
    device: "{{ adb_target }}"
    package: com.machiav3lli.fdroid
  delegate_to: localhost
```

## Role usage

`stayturgid.fdroid.fdroid_repos` and `stayturgid.play.play_store` call this
module instead of the legacy `grant_neo_store_shizuku.py` script.
