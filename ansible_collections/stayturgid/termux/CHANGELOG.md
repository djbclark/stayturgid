# Changelog — stayturgid.termux

## Unreleased

- A sshd listener that outlived its own binary is now restarted, and a login that resets
  before the banner now fails the play (p7a, 2026-11-21: an `openssh` upgrade under a running
  listener reset every login, 242 times, while `sshd -t`, `sv status` and the open port all
  passed). Three parts:
  - `termux_ssh_bootstrap` (`ensure_sshd`) checks the running listener over adb: its
    `/proc/PID/exe` ends in `(deleted)`, or it started before `bin/sshd` or
    `libexec/sshd-session` changed. A stale one is restarted (`sv restart` under runit, kill
    plus retype from the Termux app for a bare listener) and reported `changed`.
  - `termux_sshd` gets `restart_stale` (same check on the phone, `sv restart`, verified
    fresh). `termux_userland` runs it straight after the package steps and the nightly
    `termux-pkg-upgrade.yml` runs it after the upgrade, replacing the `sv hup` handler and the
    `failed_when: false` HUP, which could not tell whether the cure worked. State-based, so a
    listener an earlier aborted run left stale is cured too.
  - New module `termux_ssh_probe` (control node, `delegate_to: localhost`): reads the banner,
    sends one and requires the server's first packet to be `SSH_MSG_KEXINIT`. Run after
    `bootstrap.yml`'s bootstrap, in `fleet.yml`'s `post_tasks` (after the role's handlers) and
    in the nightly; a reset fails with `kex_exchange_identification`.
- `termux_ssh_bootstrap`, `termux_pkg`, `termux_sshd`, `termux_screen_ready` and
  `stayturgid_repair_check` no longer let Ansible expand `$HOME` or `$PATH` in the commands they
  run (`plain_run_command` from `stayturgid.android_common`, 2026-11-21). Fixes the s24 fallback
  bootstrap, where the phone ran `mkdir` on the Mac's home path, and the existing-keys check that
  always read nothing, so it can now report `changed: false`.
- `termux_userland` puts sshd under runit on a fresh Termux (`tasks/runit_sshd.yml`):
  when `sv status sshd` fails it starts one runsvdir and retires only the bare
  listener (detached), then verifies; a supervised device is unchanged.
- Phones' `authorized_keys` get only `stayturgid_ssh_public_key_files` (default
  `termux_key.pub`), no longer every `*.pub` of the control node; the operator's
  personal keys are removed by name (`stayturgid_ssh_retired_public_key_names`).
  `termux_ssh_bootstrap` likewise defaults to `termux_key.pub`.

## 1.8.0 (2026-07-09)

- `termux_ssh_bootstrap` module and `termux_run_as` module_utils — pre-SSH
  bootstrap over adb (`authorized_keys`, optional `openssh` + `sshd`).
- `ansible/playbooks/fleet/bootstrap.yml` play; conditional bootstrap via `fleet/preflight.yml`
  at the start of `site.yml` (including when launched via `deploy_fleet.py`).
  `control/bin/deploy_termux.py` still runs `fleet/bootstrap.yml` when SSH preflight fails.
- `control/lib/termux_ssh_bootstrap.py` refactored to thin CLI wrapper over
  collection helpers (direct adb path + `run_bootstrap_playbook()`).

## 1.7.0 (2026-07-09)

- Fleet SSH mesh: per-device `id_ed25519_fleet` identity; every fleet member's
  device pubkey in every `authorized_keys` via `ansible.posix.authorized_key`;
  full peer `known_hosts` mesh via `ansible.builtin.known_hosts` (inventory name,
  Tailscale IP, LAN IP aliases). `control_node/agents` trusts fleet sshd host keys on the
  control node.

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
