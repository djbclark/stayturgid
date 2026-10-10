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

Lockdown interlock (#289): `stayturgid_always_on_vpn_lockdown: true` is honoured only when the device holds a tailnet address (100.64.0.0/10) on a tun interface, the adb target is a USB serial (an mDNS wireless-debugging id such as `adb-SERIAL-xxxx._adb-tls-connect._tcp` counts as LAN, not USB) or that same address, `ansible_host` is that address, and the control node can open a TCP connection to `ansible_host:ansible_port`. Otherwise `android_settings` writes lockdown `0` and prints a warning naming the failed check. After a real write it re-checks the tailnet address and the management path twice, about 2 s and 6 s after the write, and reverts to `0` if either is gone in either round; if even the revert fails the task fails with USB recovery steps. `stayturgid_always_on_vpn_lockdown_strict: true` turns a refused or reverted lockdown into a failed task for that host. The device-side repairers (`stayturgid_repair.py`, the native agent's `CatastrophicRepair`) still force lockdown to `0` every cycle, so enabling it fleet-wide needs those changed too. Design, failure modes and the device verification steps: [docs/operations/deep-dives/tailscale-lockdown-interlock.md](../../../../../docs/operations/deep-dives/tailscale-lockdown-interlock.md).

Does not sign in to Tailscale — only configures always-on VPN once the app is installed and logged in.
