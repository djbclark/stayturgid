# Changelog — stayturgid.termux

## 1.6.0 (2026-07-09)

- Fleet SSH mesh: `ansible.posix.authorized_key` for all `*.pub` keys under
  `stayturgid_ssh_keys_dir`; private keys copied to each device; `termux_sshd`
  now manages sshd_config + detached restart only.

## 1.5.0 (2026-07-08)

- `stayturgid_repair_check` module — run repair script and parse STATUS line.

## 1.4.0 (2026-07-07)

- `termux_sshd` module; role uses it for keys + PerSourcePenalties.

## 1.3.0 (2026-07-07)

- `termux_userland` role ships in collection.

## 1.0.0

- `termux_pkg` module.
