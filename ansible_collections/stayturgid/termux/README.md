# stayturgid.termux

Termux package management over SSH.

- **Modules:** `stayturgid.termux.termux_pkg`, `termux_sshd`, `termux_ssh_bootstrap`
- **Role:** `stayturgid.termux.termux_userland` (in this collection)
- **Docs:** [termux_pkg.md](../../../docs/ansible/collections/modules/termux_pkg.md),
  [termux_ssh_bootstrap.md](../../../docs/ansible/collections/modules/termux_ssh_bootstrap.md)

Install with `stayturgid.android_common` (for `android_appops` permission grants,
`adb_device` lookup for bootstrap) and `ansible.posix` (for `authorized_key` in
`termux_userland`).
