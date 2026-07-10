# Changelog — stayturgid.fdroid

## 1.4.2 (2026-07-09)

- Add `fdroid_apps` module and `stayturgid_fdroid_apps` role var (symmetric to
  `stayturgid_play_apps` / `play_apps`).
- Extract shared `fdroidcl_install` module_utils for `fdroid_install` + `fdroid_apps`.

## 1.4.1 (2026-07-08)

- `fdroid_repos` role: fix `android_packages` lookup folded to empty by YAML `>-`.

## 1.4.0 (2026-07-07)

- Add `fdroid_install` and `fdroid_repo_push` modules.
- `fdroid_repos`: repo removal, setups, fingerprint validation.
- Role uses lookups + `fdroid_repo_push` (multi-component intent fallback).

## 1.3.0 (2026-07-07)

- Split from `stayturgid.fleet`; `fdroid_repos` module + role.
