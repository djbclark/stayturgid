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

Does not sign in to Tailscale — only configures always-on VPN once the app is installed and logged in.
