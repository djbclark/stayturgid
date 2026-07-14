# android_apk

FQCN: `stayturgid.android_common.android_apk`

Download and install an APK via adb with `INSTALL_FAILED_*` parsing.

## Parameters

| Parameter      | Description                                     |
| -------------- | ----------------------------------------------- |
| `device`       | ADB serial or `host:5555`                       |
| `package`      | Package id for idempotence check                |
| `apk_path`     | Local APK (one of `apk_path`, `url`, `gh_repo`) |
| `url`          | Download URL                                    |
| `gh_repo`      | GitHub `owner/repo` (needs `gh` CLI)            |
| `gh_pattern`   | Asset glob for `gh release download`            |
| `gh_tag`       | Release tag (default latest)                    |
| `version_name` | Install only when installed version differs     |
| `force`        | Reinstall even when present                     |
| `installer`    | Spoof installer package (`adb install -i`)      |
| `extra_args`   | Extra adb install flags                         |

## Example

```yaml
- stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: moe.shizuku.privileged.api
    gh_repo: thedjchi/Shizuku
    gh_pattern: "*.apk"
  delegate_to: localhost
```
