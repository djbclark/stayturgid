# termux_pkg

**FQCN:** `stayturgid.termux.termux_pkg`  
**Runs on:** device (Termux over SSH)

Non-interactive `pkg update` / `pkg upgrade` / `pkg install` with `--force-confold`
and recovery for stuck dpkg states.

## Example

```yaml
- stayturgid.termux.termux_pkg:
    name:
      - openssh
      - android-tools
      - termux-api
    state: present
    update_cache: true
    upgrade: true
```

## Role

See `stayturgid.termux.termux_userland` role in the `stayturgid.termux` collection
(packages, boot scripts, `authorized_key`, appops grants).

## Tests

`ansible_collections/stayturgid/termux/tests/unit/`
