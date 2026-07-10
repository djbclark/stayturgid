# stayturgid_repair_check

FQCN: `stayturgid.termux.stayturgid_repair_check`

Run on-device `stayturgid_repair.py` over the Termux SSH connection and parse
the `STATUS` line into structured fields (port, shizuku, sshd, a11y, wifi,
`et_cfg`, …). Used by the fleet validate role.

## Parameters

| Parameter | Description |
|-----------|-------------|
| `repair_script` | Path on device (default `~/.stayturgid/bin/stayturgid_repair.py`) |
| `termux_prefix` | Termux prefix (default `/data/data/com.termux/files/usr`) |
| `fail_on_unhealthy` | Fail the task when STATUS is unhealthy (default `false` — return `healthy=false`) |

## Healthy rule

`healthy=true` when `port=open` **or** `port=skip` (Fire OS without localhost
loopback). Matches device-tier `parse_heal`.

## Example

```yaml
- name: Verify repair layer after deploy
  stayturgid.termux.stayturgid_repair_check:
    fail_on_unhealthy: true
```

## See also

- [roles/validate.md](../roles/validate.md)
- On-device script: `device/termux/py/stayturgid_repair.py`
