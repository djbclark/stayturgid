# Standard Ansible modules vs stayturgid custom modules

Audit of what the fleet Ansible layer does today and whether well-established
modules could replace custom code.

## Already using Ansible builtins / collection modules

| Task                           | Module / lookup                              | Role                                                                         |
| ------------------------------ | -------------------------------------------- | ---------------------------------------------------------------------------- |
| SSH public keys (steady state) | `ansible.posix.authorized_key`               | `termux_userland`                                                            |
| SSH bootstrap (pre-SSH, adb)   | `stayturgid.termux.termux_ssh_bootstrap`     | `preflight.yml`, `bootstrap.yml`                                             |
| sshd config + restart          | `stayturgid.termux.termux_sshd`              | `termux_userland`                                                            |
| Package mirror / scripts       | `ansible.builtin.copy`                       | `termux_userland`                                                            |
| Termux packages                | `stayturgid.termux.termux_pkg`               | `termux_userland`                                                            |
| ADB alias resolve              | `stayturgid.android_common.adb_device`       | play, shizuku_config, app_privileges, post_ui, validate, bootstrap playbooks |
| Package detection              | `stayturgid.android_common.android_packages` | validate                                                                     |
| F-Droid client component       | `stayturgid.android_common.fdroid_client`    | none (legacy; F-Droid automation removed in #119)                            |
| Unified app ensure             | `stayturgid.android_common.ensure_apps`      | fleet (optional)                                                             |

## Custom modules (required — no upstream equivalent)

| Module                                | Why custom                                         |
| ------------------------------------- | -------------------------------------------------- |
| `termux_pkg`                          | Termux pkg/apt, not system apt                     |
| `play_apps`                           | apkeep/gplaycli + adb install                      |
| `android_appops` / `android_settings` | adb grants/settings                                |
| `android_a11y_services`               | merge-only a11y list backup/restore                |
| `shizuku_grant`                       | pm grant + conditional Shizuku server restart      |
| `android_apk` / `android_intent`      | adb install / intents                              |
| `termux_ssh_bootstrap`                | Pre-SSH adb + `run-as` key install (no SSH yet)    |
| `android_app_privileges`              | adb privilege grants for the `app_privileges` role |
| `native_agent_config`                 | Native-agent peer configuration over ADB           |
| `shizuku_start`                       | Start Shizuku over ADB and apply the fleet profile |
| `stayturgid_verify`                   | Device state verification and drift detection      |

## Shell tasks — remaining

| Task                   | Role                                        | Status                        |
| ---------------------- | ------------------------------------------- | ----------------------------- |
| Termux `/sdcard` mkdir | `termux_userland`                           | Keep — Fire symlink quirks    |
| Repair verify          | `stayturgid.termux.stayturgid_repair_check` | `termux_userland`, `validate` |
| Boot loop handler      | `termux_userland`                           | Keep — PIDFILE semantics      |

## Distribution

1. Domain collections with `CHANGELOG.md` per collection.
2. Git tags `stayturgid.<collection>-<version>`.
3. Consumer templates under `examples/consumer-*`.
4. Galaxy publish — optional follow-up.

## Deprecated

- `control/tools/fdroid/grant_neo_store_shizuku.py` — **removed stub**; use `stayturgid.android_common.shizuku_grant`.
