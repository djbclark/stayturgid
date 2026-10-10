# tailscale_vpn

Sets Android `always_on_vpn_app` to Tailscale via privileged adb on the control Mac (works on Fire OS where Termux loopback adb does not).

Defaults (`group_vars/all.yml`):

- `stayturgid_always_on_vpn: true`
- `stayturgid_always_on_vpn_lockdown: false` — do **not** enable "Block connections without VPN" (breaks LAN ADB when tun0 is down)

Included in `fleet.yml` after `obtainium_apps` (Tailscale must be installed).

```bash
./control/bin/deploy_fleet.py          # all hosts
./control/bin/deploy_fleet.py fireos-device      # one host
```

Lockdown interlock (#289): `stayturgid_always_on_vpn_lockdown: true` is honoured only when the device holds a tailnet address (100.64.0.0/10) on a tun interface, `ansible_host` is that address, and the control node can open a TCP connection to `ansible_host:ansible_port`. Otherwise `android_settings` writes lockdown `0` and prints a warning naming the failed check. The device-side repairers (`stayturgid_repair.py`, the native agent's `CatastrophicRepair`) also force lockdown to `0`, so enabling it fleet-wide needs those changed too.

Does not sign in to Tailscale — only configures always-on VPN once the app is installed and logged in.
