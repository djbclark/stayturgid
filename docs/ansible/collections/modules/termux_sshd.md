# termux_sshd

FQCN: `stayturgid.termux.termux_sshd`

Manage Termux `sshd_config` and detached sshd restart. SSH public keys are
managed by `ansible.posix.authorized_key` in the `termux_userland` role.

## Parameters

| Parameter           | Description                                                   |
| ------------------- | ------------------------------------------------------------- |
| `config`            | Dict of sshd_config options (`{PerSourcePenalties: "no"}`)    |
| `restart_on_change` | Detached restart when config changes (default `true`)         |
| `ensure_running`    | Remove a stale runsv `down` file (default `true`)             |
| `restart_stale`     | Restart a listener that outlived its binary (default `false`) |
| `termux_prefix`     | Termux prefix                                                 |

## Example

```yaml
- stayturgid.termux.termux_sshd:
    config:
      PerSourcePenalties: "no"
```

## Stale listener (`restart_stale`)

An `openssh` package upgrade replaces `sshd`, `sshd-session` and `sshd-auth` under a running
listener, which then resets every login before the banner (`kex_exchange_identification`; p7a,
2026-11-21). With `restart_stale: true` the module reads the listener (pid from
`$PREFIX/var/run/sshd.pid`) and treats it as stale when `/proc/PID/exe` ends in `(deleted)` or
the listener started before `bin/sshd` or `libexec/sshd-session` last changed. A stale listener
under runit is restarted with `sv restart sshd` (sessions survive) and must read fresh
afterwards; a bare one is only warned about. An unreadable pidfile or `/proc` entry is
`unknown` and never restarts. Returns `stale_listener` and `stale_restarted`.

```yaml
- stayturgid.termux.termux_sshd:
    restart_stale: true
    ensure_running: false
```

## Role usage

`stayturgid.termux.termux_userland` uses `ansible.posix.authorized_key` for the
fleet keyring and this module for `PerSourcePenalties no` lockout prevention.
