# termux_sshd

FQCN: `stayturgid.termux.termux_sshd`

Manage Termux `authorized_keys`, `sshd_config`, and detached sshd restart in
one module — replaces `ansible.posix.authorized_key` + `lineinfile` + handler
for the common Termux sshd bootstrap path.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `keys` | SSH public key lines to ensure |
| `exclusive` | Remove keys not in `keys` (default `false`) |
| `authorized_keys_path` | Path to authorized_keys |
| `config` | Dict of sshd_config options (`{PerSourcePenalties: "no"}`) |
| `restart_on_change` | Detached restart when config changes (default `true`) |
| `termux_prefix` | Termux prefix |

## Example

```yaml
- stayturgid.termux.termux_sshd:
    keys: "{{ my_pubkey_lines }}"
    exclusive: false
    config:
      PerSourcePenalties: "no"
```

## Role usage

`stayturgid.termux.termux_userland` uses this for operator keys and
`PerSourcePenalties no` lockout prevention.
