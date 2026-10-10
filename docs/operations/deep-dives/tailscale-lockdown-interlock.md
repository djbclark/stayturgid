# Always-on VPN lockdown interlock (issue #289)

**Issue:** https://github.com/djbclark/stayturgid/issues/289
**Date:** 2026-10-09 (ClaudeHelm; night run wrote the pre-check, evening run added the adb-path check, the post-write back-off, strict mode and this note)
**Status:** Implemented in `stayturgid.android_common.android_settings` and the `tailscale_vpn` role, unit-tested, **not yet verified on a device** (steps in section 6)
**Scope:** The control-node side of enabling Android's "Block connections without VPN" for Tailscale. Tailscale login itself is still manual (see section 7).

## 1. The hazard

`secure/always_on_vpn_lockdown=1` makes Android drop every packet that does not go through the always-on VPN app. If Tailscale is not logged in, or its tunnel never comes up, the device loses ADB-over-TCP, Termux SSH, the agent's Mac-side channel and everything else at once. Nothing in this repo logs the device in to Tailscale, so a from-scratch provision is unauthenticated by definition. Recovery is USB or a factory reset. Until this change the role wrote the flag straight from `stayturgid_always_on_vpn_lockdown` with no check.

## 2. Design

The interlock lives in the module, not the role, so it also guards a hand-written task and any future caller. It runs on the control node (`delegate_to: localhost`) and talks to the device over adb, the same way the role does.

### 2.1 Pre-check (before any write)

A request for lockdown `1` is honoured only when all four hold, checked in this order:

| #   | Check                                                                                                                                                 | Why                                                                                                                                  |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | `ip -4 -o addr show` on the device shows a `tunN` or `tailscale*` interface holding an IPv4 in `100.64.0.0/10`                                        | Only a logged-in, connected Tailscale client has a tailnet address. Any TUN index counts (the fleet sees `tun1`); `tunl0` never does |
| 2   | The adb target (`device`) is a USB serial (not an mDNS `._adb-tls-connect._tcp` service id), or a `host:port` whose host is that same tailnet address | Lockdown can cut a LAN or mDNS adb path, and that path is what the module would need to revert the write                             |
| 3   | `lockdown_management_host` (the role passes `ansible_host`) is that same tailnet address                                                              | Proves Ansible already reaches this device over the VPN, and that the inventory address is not stale                                 |
| 4   | A TCP connect from the control node to `lockdown_management_host:lockdown_management_port` (`ansible_port`, 8022)                                     | Proves the data path through the tunnel works end to end, from this control node, right now                                          |

On any failure the module rewrites the request to `0`, writes that, warns with the failed check, and returns `lockdown_interlock: {blocked: true, stage: precheck, reason, device_tailnet_ip}`. A request for `0` skips the interlock. Check mode runs the pre-check (reads only) and reports `would_set`.

"Control connection healthy" is deliberately measured as a TCP connect to the device's sshd over the tailnet rather than a ping to `controlplane.tailscale.com` from the device: the TCP probe exercises the exact path lockdown must not break, from the exact host that needs it, and it cannot pass on a stale tunnel. The device-side repairers keep their control-plane ping for their own purposes.

### 2.2 Post-write verification and back-off

When `1` was actually written (status `set`, not check mode, not `already`), the module probes twice, at the offsets in `LOCKDOWN_PROBE_AT_SECONDS` (about 2 s and 6 s after the write, so firewall rules that Android applies a few seconds late are still caught). Each round re-reads the tailnet address over adb and re-probes the management path, and both rounds must pass before the result is `verified`. If any check fails it writes `0` back, marks the result `reverted`, warns, and returns `stage: post_write`. If that revert write fails the module fails the task with the USB recovery command, because the device may now be cut off.

### 2.3 Strict mode

The issue asked for a loud failure; the night run chose warn-and-write-0 so one unauthenticated device still receives the rest of its deploy. Both are available: `stayturgid_always_on_vpn_lockdown_strict: true` turns a refused or reverted lockdown into a failed task for that host (`failed_when` on `lockdown_interlock.blocked`). Default `false`. Ansible's default per-host failure handling means a strict failure drops only that host from the remainder of the play.

### 2.4 What the interlock does not do

1. It does not log the device in (section 7).
2. It does not keep lockdown on: the device-side repairers write `0` every cycle (failure mode 10).
3. It does not protect against a later loss of the tunnel (failure mode 11).

## 3. Failure modes

| #   | Situation                                                                                                                                     | What happens                                                                                             | Operator action                                                                                                                      |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Tailscale installed but never logged in, logged out, or tunnel down                                                                           | Refused at pre-check 1; lockdown written `0`; warning "not logged in and connected"                      | Log in on the device (one-time manual step), rerun                                                                                   |
| 2   | adb resolved over LAN `:5555`, a wireless-debugging mDNS `ip:port`, or a colon-less mDNS service id (`adb-SERIAL-xxxx._adb-tls-connect._tcp`) | Refused at pre-check 2; `0` written                                                                      | Attach USB, or make the device resolve over its tailnet address (`adb connect <tailnet-ip>:5555`)                                    |
| 3   | adb target is a tailnet address but not this device's                                                                                         | Refused at pre-check 2                                                                                   | Fix `devices.conf` / inventory; the lookup resolved the wrong device                                                                 |
| 4   | `ansible_host` is a LAN address                                                                                                               | Refused at pre-check 3; "lockdown would cut that path"                                                   | Manage the device over its tailnet address before enabling lockdown                                                                  |
| 5   | `ansible_host` is a tailnet address but not the one the device holds (stale inventory)                                                        | Refused at pre-check 3                                                                                   | Correct the inventory                                                                                                                |
| 6   | Device sshd down or port 8022 blocked (the 2026-10-08 s24 wedge)                                                                              | Refused at pre-check 4 even though the tunnel is fine. A false negative that errs on the safe side       | Fix sshd first; the deploy needs it anyway                                                                                           |
| 7   | Management path dies within about 6 s of the write (either probe round)                                                                       | Reverted to `0` (`stage: post_write`), warning                                                           | Investigate why the tunnel or sshd dropped; rerun                                                                                    |
| 8   | Tailnet address disappears (or adb stops answering) right after the write                                                                     | Reverted to `0`                                                                                          | Same as 7. If adb stopped answering over the tailnet the revert itself goes over the same path and may hit 9                         |
| 9   | Post-write verification fails **and** the revert write fails                                                                                  | Task fails: "connect it over USB and run `adb shell settings put secure always_on_vpn_lockdown 0`"       | USB: `adb -s <serial> shell settings put secure always_on_vpn_lockdown 0`. Without adb: Settings > Network > VPN > gear > off        |
| 10  | Lockdown `1` is written and verified, then the Termux loop (≤15 min) or agent (≤20 min) runs                                                  | They write `always_on_vpn_lockdown=0` unconditionally; `ComonitorProbes` even reports `1` as policy down | Expected today. Lockdown cannot be durable until the device copies read the policy from `device.json` (audit, section 4 item 2)      |
| 11  | Lockdown durable (after 10 is fixed) and the node key expires, or the account is logged out                                                   | Tunnel never comes back; device is severed at the next reconnect                                         | Before any fleet enable, disable key expiry for fleet nodes in the Tailscale admin console. The interlock cannot see a future expiry |
| 12  | Device already has lockdown `1` and a pre-check fails on this run                                                                             | The module writes `0` (back-off applies to existing state too)                                           | Deliberate: a device whose checks fail is one lockdown may have already cut off                                                      |
| 13  | Lockdown already `1`, all checks pass                                                                                                         | Status `already`; no post-write probe (nothing written)                                                  | None                                                                                                                                 |
| 14  | Check mode                                                                                                                                    | Pre-check runs (reads only), no write, no settle, no post-write probe                                    | Use it as the first verification step                                                                                                |

## 4. Interaction with the repair paths (#201)

Both device-side repairers hard-code lockdown `0`, and the agent's probe treats anything else as a broken policy. So today `stayturgid_always_on_vpn_lockdown: true` is interlocked at deploy and then undone by the device within one cycle. That is a safety net, not a bug to fix in isolation: the fix is to render the always-on and lockdown policy into `device.json` and have both copies read it, which is step 1 of the consolidation in [tailscale-repair-redundancy-audit.md](../tailscale-repair-redundancy-audit.md). Do that only after the field verification below has shown the interlock behaving on a real device, and only with key expiry disabled (failure mode 11).

## 5. Tests

`ansible_collections/stayturgid/android_common/tests/unit/plugins/modules/test_android_settings.py`: 16 interlock cases. Every pre-check refusal, the allowed path over USB and over the tailnet, the lockdown-`0` bypass, the interface parser, the adb-target classifier, both post-write reverts, the revert-failed task failure with recovery text, and check mode never probing after. Run:

```bash
cd ansible_collections/stayturgid/android_common && \
  ../../../.venv-test/bin/ansible-test units --local \
  --python-interpreter ../../../.venv-test/bin/python \
  tests/unit/plugins/modules/test_android_settings.py
```

## 6. Device verification (queued; needs a device and the operator)

Preconditions: one shell-capable phone (test order s24, hd8, p7a), **attached over USB for the whole exercise** so a bad outcome is one adb command away, Tailscale logged in, inventory `ansible_host` = its tailnet address. Announce the device use first. Everything below is one host; nothing is pushed to inventory. The lockdown values are passed with `-e`, so `group_vars` stays at `false`.

```bash
cd ${OPS_ROOT:-~/ops}/stayturgid
H=s24   # inventory host
S=$(adb devices | awk 'NR>1 && $2=="device" && $1 !~ /:/ {print $1}' | head -1); echo "usb=$S"
cat > /tmp/lockdown-289.yml <<'EOF2'
- hosts: "{{ target }}"
  gather_facts: false
  roles:
    - role: stayturgid.android_common.tailscale_vpn
EOF2
PB="ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook /tmp/lockdown-289.yml -e target=$H -v"
```

1. **Baseline.** `adb -s $S shell settings get secure always_on_vpn_lockdown` prints `0`. `ssh $H true` succeeds.
2. **Check mode, authenticated.** `eval $PB --check --diff -e stayturgid_always_on_vpn_lockdown=true`. Expect `lockdown_interlock.stage: verified`, both results `would_set`, no warning, and the device still at `0`.
3. **Refusal, tunnel down.** On the phone, disconnect Tailscale from its notification (or the app's toggle). `eval $PB -e stayturgid_always_on_vpn_lockdown=true`. Expect a warning "always_on_vpn_lockdown=1 refused ... not logged in and connected", `stage: precheck`, and `settings get` still `0`. Reconnect Tailscale and confirm `ssh $H true` works again.
4. **Refusal, LAN adb.** Only if the device also answers on LAN: `adb disconnect; adb connect <lan-ip>:5555`, unplug USB, rerun step 3's command. Expect "adb target ... is a LAN or mDNS path". Replug USB.
5. **Enable, with USB as the safety net.** `eval $PB -e stayturgid_always_on_vpn_lockdown=true`. Expect `stage: verified`, lockdown result `set`, no warning. Then, within a minute: `adb -s $S shell settings get secure always_on_vpn_lockdown` prints `1`; `ssh $H true` succeeds; `adb connect <tailnet-ip>:5555` succeeds. If any of those fail: `adb -s $S shell settings put secure always_on_vpn_lockdown 0` immediately and record which one.
6. **Observe the device-side revert (failure mode 10).** Poll `adb -s $S shell settings get secure always_on_vpn_lockdown` every few minutes; within 20 min it returns to `0`, and `watchdog.log` or `agent.log` shows the always-on policy write. Record which copy did it and after how long.
7. **Strict mode.** With Tailscale disconnected again: `eval $PB -e stayturgid_always_on_vpn_lockdown=true -e stayturgid_always_on_vpn_lockdown_strict=true`. Expect the task to fail for `$H` with the interlock reason. Reconnect Tailscale.
8. **Restore.** `eval $PB` (defaults) and confirm `0`, `ssh $H true`, and the agent STATUS line shows `tailscale_policy=up`.

The post-write revert (failure modes 7 to 9) cannot be provoked safely on a real device; it is covered by unit tests only.

## 7. The seam for future auth

Nothing here authenticates Tailscale. The issue records the constraints: no `dpm set-device-owner` (the slot is reserved for Island/Insular), so managed configuration delivery would be via Shizuku's privileged context (unproven) or a documented one-time manual login (acceptable). An auth key would come from secretspec at apply time and must rotate. When either lands, it belongs before this role in `fleet.yml`, and the interlock stays exactly where it is: it is what proves the login worked before lockdown is allowed.
