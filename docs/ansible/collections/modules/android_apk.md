# android_apk

FQCN: `stayturgid.android_common.android_apk`

Download and install an APK via adb with `INSTALL_FAILED_*` parsing.

## Parameters

| Parameter               | Description                                                      |
| ----------------------- | ---------------------------------------------------------------- |
| `device`                | ADB serial or `host:5555`                                        |
| `package`               | Package id for idempotence check                                 |
| `apk_path`              | Local APK (one of path, URL, or GitHub repo)                     |
| `url`                   | Download URL                                                     |
| `gh_repo`               | GitHub `owner/repo` (needs `gh` CLI)                             |
| `gh_pattern`            | Asset glob for `gh release download`                             |
| `gh_tag`                | Release tag (default latest)                                     |
| `gh_latest`             | Follow the newest release; digest-verified                       |
| `gh_tag_prefix`         | With `gh_latest`: only tags that are this prefix plus an integer |
| `gh_skip_prereleases`   | With `gh_latest`: skip prereleases (false)                       |
| `signer_sha256`         | Only this signing cert; package must match                       |
| `version_name`          | Install only when installed version differs                      |
| `checksum`              | Expected pre-resigning SHA-256                                   |
| `force`                 | Reinstall even when present                                      |
| `clean_on_incompatible` | Clean retry for signature/version conflicts                      |
| `installer`             | Spoof installer package (`adb install -i`)                       |
| `extra_args`            | Extra adb install flags                                          |

## Example

```yaml
- stayturgid.android_common.android_apk:
    device: "{{ adb_target }}"
    package: org.stayturgid.agent
    gh_repo: djbclark/stayturgid
    gh_latest: true
    gh_tag_prefix: agent-r
    gh_pattern: app-release.apk
  delegate_to: localhost
```

This follows the newest `agent-r*` release, which is how the fleet installs the
agent and every GitHub-hosted app except Tailscale. The installed app is
compared by SHA-256 against the digest GitHub publishes for the asset;
`gh_latest` excludes `gh_tag`, `version_name` and `checksum`, and
`gh_tag_prefix` excludes `gh_tag`. `gh_tag_prefix` and `gh_skip_prereleases`
need `gh_latest`; both are part of the remembered-release key
(`gh_latest_pin_to_cache`), and with either set the module lists 100 releases
instead of 10.

A release-locked entry (still used for Tailscale) instead supplies `gh_tag`, an
exact asset filename in `gh_pattern`, `version_name`, and `checksum`.
