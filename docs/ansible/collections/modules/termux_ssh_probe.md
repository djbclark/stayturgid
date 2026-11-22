# termux_ssh_probe

FQCN: `stayturgid.termux.termux_ssh_probe`

Banner and key-exchange probe of a phone's sshd, from the control node
(`delegate_to: localhost`). It reads the server's identification string, sends one, and
requires the server's first packet to be `SSH_MSG_KEXINIT`. No keys, no authentication.

It catches what `sshd -t`, `sv status` and an open port cannot: a listener that accepts the
connection and resets it before the banner (`kex_exchange_identification: Connection reset by
peer`), as a stale listener does after an `openssh` upgrade (p7a, 2026-11-21).

## Parameters

| Parameter | Description                                  |
| --------- | -------------------------------------------- |
| `host`    | Address or name to probe (required)          |
| `port`    | sshd port (default `8022`)                   |
| `timeout` | Seconds per connect and read (default `8.0`) |
| `retries` | Attempts before failing (default `1`)        |
| `delay`   | Seconds between attempts (default `3.0`)     |

Returns `banner` and `attempts`; never `changed`; runs in check mode.

## Example

```yaml
- stayturgid.termux.termux_ssh_probe:
    # delegate_to: localhost makes ansible_host/ansible_port mean localhost's.
    host: "{{ hostvars[inventory_hostname].ansible_host | default(inventory_hostname) }}"
    port: "{{ hostvars[inventory_hostname].ansible_port | default(8022) }}"
    retries: 5
  delegate_to: localhost
```

## Where it runs

`bootstrap.yml` (after the bootstrap module), `fleet.yml` (`post_tasks`, after the role's
handlers) and `termux-pkg-upgrade.yml` (after the sshd restart check).
