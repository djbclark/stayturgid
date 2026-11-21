# Changelog — stayturgid.play

## Unreleased

- `play_apps` no longer lets Ansible expand `$VAR` and `~` in the commands it runs (`plain_run_command` from
  `stayturgid.android_common` 1.6.0, 2026-11-21). `apkeep_bin`, `gplaycli_bin` and `repo_root` are now
  `type: path`, so a leading `~` or a variable in them is still expanded, by Ansible's argument parser.

## 1.4.0 (2026-07-07)

- `play_store` role uses `android_packages` lookup (no shell pm list).

## 1.3.0 (2026-07-07)

- `play_apps` module + `play_store` role; optional `android_apk` Aurora install.
