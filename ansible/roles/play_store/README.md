# play_store (skeleton)

Ansible role skeleton for Google Play / Aurora Store support (FOSS Play client), symmetric to fdroid_repos / Neo Store.

## Status (as of handoff)
- Aurora Store added to Obtainium catalog.
- Basic role with target_device, grant (reuses generalized helper), and notes.
- gplaycli installed on control (pip; has protobuf/pkg_resources compatibility issues — may need venv or fixes).
- No full "repo" concept like F-Droid; focus on client setup + download+install with installer spoof (`-i com.android.vending`).

## Usage (example)
```yaml
- hosts: stayturgid
  roles:
    - play_store
  vars:
    target_device: p7a
```

Run after obtainium_apps.

See HANDOFF.md ("Side project: fdroid_repos / play_store") for next actions and full context.

This is experimental side work.
