# adb_device (lookup)

FQCN: `stayturgid.android_common.adb_device`

**Lookup plugin** (not a module): resolve a fleet inventory alias to an ADB
serial or `host:5555` on the control node.

## Behaviour

1. Reads `~/.config/stayturgid/devices.conf` (or `STAYTURGID_DEVICES_CONF`)
2. Prefers USB serial when that device is connected
3. Otherwise tries LAN then Tailscale `ip:5555` (may `adb connect`)
4. Scans connected devices by `ro.serialno` when inventory IPs drift
5. Unknown aliases pass through unchanged (raw serial or `host:port`)

## Example

```yaml
- name: Grant Shizuku using resolved ADB target
  ansible.builtin.command:
    argv:
      - python3
      - grant.py
      - "{{ lookup('stayturgid.android_common.adb_device', inventory_hostname) }}"
  delegate_to: localhost
```

## See also

- Python twin: `control/lib/stayturgid_device.py` (`resolve_adb`, `device_row`)
- Module util: `plugins/module_utils/adb_resolve.py`
