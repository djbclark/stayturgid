# Standard Ansible modules vs stayturgid custom modules

Audit of what the fleet Ansible layer does today and whether well-established
modules could replace custom code.

## Already using Ansible builtins / collection modules

| Task | Module / lookup | Role |
|------|---------------|------|
| SSH keys + sshd config | `stayturgid.termux.termux_sshd` | `termux_userland` |
| Package mirror / scripts | `ansible.builtin.copy` | `termux_userland`, `autojs6_watchdog` |
| Termux packages | `stayturgid.termux.termux_pkg` | `termux_userland` |
| ADB alias resolve | `stayturgid.android_common.adb_device` | fdroid, play, tailscale |
| Package detection | `stayturgid.android_common.android_packages` | fdroid, play |
| F-Droid client component | `stayturgid.android_common.fdroid_client` | fdroid (via `fdroid_repo_push`) |
| Unified app ensure | `stayturgid.android_common.ensure_apps` | fleet (optional) |

## Custom modules (required — no upstream equivalent)

| Module | Why custom |
|--------|------------|
| `termux_pkg` | Termux pkg/apt, not system apt |
| `obtainium_app` | No Obtainium API |
| `fdroid_repos` / `fdroid_install` / `fdroid_repo_push` | fdroidcl wrapper |
| `play_apps` | apkeep/gplaycli + adb install |
| `android_appops` / `android_settings` | adb grants/settings |
| `shizuku_grant` | shizuku.json patch |
| `android_apk` / `android_intent` | adb install / intents |

## Shell tasks — remaining

| Task | Role | Status |
|------|------|--------|
| Fire OS `mkdir` / adb push | `autojs6_watchdog` | Keep — platform-specific |
| Termux `/sdcard` mkdir | `termux_userland` | Keep — Fire symlink quirks |
| Repair verify shell | `termux_userland` | Keep — reads device script output |
| Boot loop handler | `termux_userland` | Keep — PIDFILE semantics |

## Distribution

1. Domain collections with `CHANGELOG.md` per collection.
2. Git tags `stayturgid.<collection>-<version>`.
3. Consumer templates under `examples/consumer-*`.
4. Galaxy publish — optional follow-up.

## Deprecated

- `fdroid/mac/grant_neo_store_shizuku.py` — use `stayturgid.android_common.shizuku_grant`.
