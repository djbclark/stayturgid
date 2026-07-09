# termux_sshd

FQCN: `stayturgid.termux.termux_sshd`

Manage Termux `sshd_config` and detached sshd restart. SSH public keys are
managed by `ansible.posix.authorized_key` in the `termux_userland` role.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `config` | Dict of sshd_config options (`{PerSourcePenalties: "no"}`) |
| `restart_on_change` | Detached restart when config changes (default `true`) |
| `termux_prefix` | Termux prefix |

## Example

```yaml
- stayturgid.termux.termux_sshd:
    config:
      PerSourcePenalties: "no"
```

## Role usage

`stayturgid.termux.termux_userland` uses `ansible.posix.authorized_key` for the
fleet keyring and this module for `PerSourcePenalties no` lockout prevention.
