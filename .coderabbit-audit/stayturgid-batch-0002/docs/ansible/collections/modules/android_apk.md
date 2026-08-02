# android_apk

FQCN: `stayturgid.android_common.android_apk`

Download and install an APK via adb with `INSTALL_FAILED_*` parsing.

## Parameters

| Parameter               | Description                                  |
| ----------------------- | -------------------------------------------- |
| `device`                | ADB serial or `host:5555`                    |
| `package`               | Package id for idempotence check             |
| `apk_path`              | Local APK (one of path, URL, or GitHub repo) |
| `url`                   | Download URL                                 |
| `gh_repo`               | GitHub `owner/repo` (needs `gh` CLI)         |
| `gh_pattern`            | Asset glob for `gh release download`         |
| `gh_tag`                | Release tag (default latest)                 |
| `version_name`          | Install only when installed version differs  |
| `checksum`              | Expected pre-resigning SHA-256               |
| `force`                 | Reinstall even when present                  |
| `clean_on_incompatible` | Clean retry for signature/version conflicts  |
| `installer`             | Spoof installer package (`adb install -i`)   |
| `extra_args`            | Extra adb install flags                      |

## Example

```yaml
- stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: org.stayturgid.agent
    gh_repo: djbclark/stayturgid
    gh_tag: agent-v0.6.0
    gh_pattern: app-release.apk
    version_name: 0.6.0-boot-stability
    checksum: "sha256:..."
  delegate_to: localhost
```

Versioned fleet catalogs must supply `gh_tag`, an exact asset filename in
`gh_pattern`, `version_name`, and `checksum`; using a wildcard asset or GitHub's
mutable repository-wide latest release is only supported for ad-hoc module
callers outside the normal fleet deployment.
