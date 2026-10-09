# android_settings

FQCN: `stayturgid.android_common.android_settings`

Idempotent `settings put` over adb for `secure`, `global`, or `system` namespaces.

## Parameters

| Parameter                  | Description                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------------- |
| `device`                   | ADB serial or `host:5555`                                                                            |
| `connect`                  | Run `adb connect` first (default `true`)                                                             |
| `settings`                 | List of `{namespace, key, value}` (required)                                                         |
| `require_package`          | Skip all changes when package is not installed                                                       |
| `lockdown_management_host` | Address the control node manages the device through (`ansible_host`); used by the lockdown interlock |
| `lockdown_management_port` | TCP port on that host the interlock must reach (default `8022`, Termux sshd)                         |

## Always-on VPN lockdown interlock (#289)

A request for `secure/always_on_vpn_lockdown=1` is honoured only when the device holds a tailnet address (100.64.0.0/10) on a `tunN`/`tailscale*` interface, `device` is a USB serial or that same address, `lockdown_management_host` is that address, and a TCP connect from the control node to `lockdown_management_host:lockdown_management_port` succeeds. Otherwise the module writes `0`, warns, and returns `lockdown_interlock: {blocked: true, reason, device_tailnet_ip, stage: precheck}`. After a real write of `1` it waits two seconds, re-reads the tailnet address over adb and re-probes the management path; on any failure it writes `0` back (`stage: post_write`, result status `reverted`) and warns, and if that revert fails it fails the task with USB recovery steps. Design and failure modes: [docs/operations/deep-dives/tailscale-lockdown-interlock.md](../../../operations/deep-dives/tailscale-lockdown-interlock.md).

## Example

```yaml
- stayturgid.android_common.android_settings:
    device: "{{ adb_target }}"
    require_package: com.tailscale.ipn
    settings:
      - namespace: secure
        key: always_on_vpn_app
        value: com.tailscale.ipn
      - namespace: secure
        key: always_on_vpn_lockdown
        value: "1"
  delegate_to: localhost
```

## Role usage

`stayturgid.android_common.tailscale_vpn` uses this module for always-on VPN.
