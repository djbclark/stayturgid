# CFEngine Server Mode — Implementation Description for Web Dashboard

## Overview

A fourth independent transport (CFEngine `cf-serverd` on port 5308, TLS) has been
added to the fleet connection fallback chain. The Mac can now trigger immediate
`cf-agent` repair runs on any device via `cf-runagent`, providing a repair channel
that does not depend on ADB or SSH.

## Connection fallback chain (4 tiers)

| Tier | Transport    | Port  | Protocol | Auth                     | Status                         |
| ---- | ------------ | ----- | -------- | ------------------------ | ------------------------------ |
| 1    | ADB          | 5555  | ADB      | RSA keypair              | ✅                             |
| 2    | SSH          | 8022  | SSH      | stayturgid CA cert + key | ✅                             |
| 3a   | CFEngine     | 5308  | TLS      | Peer-to-peer key trust   | ✅ TLS proven, bundle exec WIP |
| 3b   | FIRERPA gRPC | 65000 | gRPC/TLS | gRPC auth                | ✅                             |

## New files

### Device-side (on each Android device)

| File                                                   | Purpose                                                                                                                                                                                                                      |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `device/termux/cfengine/policy/cf-serverd.cf`          | Server policy: IP ACL (Tailscale 100.64.0.0/10), access rules for 9 repair bundles, auto-trust on first connection. Specifies `cfruncommand` (wrapper script).                                                               |
| `device/termux/cfengine/policy/cf-runagent-wrapper.sh` | Shell wrapper that sets Termux PATH/LD_LIBRARY_PATH before invoking `cf-agent -f stayturgid.cf`. Needed because cf-serverd inherits minimal env.                                                                             |
| `device/termux/py/start_adb.py`                        | `startup_cfserverd()`: starts cf-serverd after sshd, before FIRERPA. `_monitor_cfserverd()`: monitors cf-serverd liveness in boot loop, restarts if dead. Uses `-F` flag (no fork — Android seccomp blocks fork for Termux). |

### Mac control-node side

| File                                                                                                          | Purpose                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `~/.config/stayturgid/cfengine/cf-runagent.cf` (rendered; example: `control/cfengine/cf-runagent.cf.example`) | Runagent policy: hosts list (all fleet devices on port 5308), background children, auto-trust. Rendered from `ansible/roles/control_node/templates/cf-runagent.cf.j2` by `just deploy-mac`; never tracked. Mac invokes via `cf-runagent -f <this-file> --remote-bundles <name> -D <class>`. |
| `~/.cfagent/ppkeys/`                                                                                          | CFEngine key store. Contains Mac private key (`localhost.priv`), Mac public key (`localhost.pub`), and trusted device keys (`root-MD5=<hash>.pub`). Keys established via `cf-key --trust-key <ip>:<keyfile>`.                                                                               |

### Ansible deploy

| File                                                                            | Change                                                                                                                                                                |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ansible_collections/stayturgid/termux/roles/termux_userland/defaults/main.yml` | Line 20: added `cfengine` to `stayturgid_termux_packages`                                                                                                             |
| `ansible_collections/stayturgid/termux/roles/termux_userland/tasks/main.yml`    | Validates/builds `device/termux/cfengine/cfbs.json` locally, then deploys `stayturgid.cf`, `cf-serverd.cf`, and `cf-runagent-wrapper.sh` to `~/.stayturgid/cfengine/` |

### Fleet health integration

| File                                  | Change                                                                                                                                                                                  |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `control/lib/fleet_health.py`         | Lines 109-116: `HEALTH_GATHER` scrapes `repair-cfengine.log`, reports `cfengine=ok                                                                                                      | down`. Lines 226-227: flags `cfengine_down`as a non-critical issue. Lines 244: includes`cfengine=` in summary. |
| `control/bin/fleet_health_monitor.py` | Lines 359-381: `_try_firerpa_heal_fallback()` probes port 65000 and triggers FIRERPA heal when ADB+SSH are both down. CFEngine cf-runagent trigger planned as Tier 3a (before FIRERPA). |

### Documentation

| File                                     | Change                                                                                                                                                                                                      |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/handoff.md`                        | Lines 260-281: CFEngine server mode section in Major changes. Lines 173-175: cf-serverd column in fleet snapshot. Lines 433-450: updated remote-access architecture with 4-tier chain + 5 on-device layers. |
| `docs/architecture/core-architecture.md` | Lines 58-93: new "Connection fallback chain" and "On-device self-heal layers" sections replacing the old single-paragraph description.                                                                      |
| `AGENTS.md`                              | CFEngine-related key commands.                                                                                                                                                                              |

## Device runtime state

| State file                                                 | Purpose                                       |
| ---------------------------------------------------------- | --------------------------------------------- |
| `~/.stayturgid/run/cf-serverd.pid`                         | cf-serverd PID file (for liveness monitoring) |
| `~/.stayturgid/logs/cf-serverd.log`                        | cf-serverd daemon log                         |
| `~/.stayturgid/logs/repair-cfengine.log`                   | cf-agent (standalone boot-loop run) log       |
| `/data/data/com.termux/files/usr/var/lib/cfengine/ppkeys/` | CFEngine key store on device                  |

## Dashboard integration suggestions

### New health indicators to show

1. **cf-serverd status** — already reported as `cfengine=ok|down` in fleet-health.log. The existing `just health` output includes it. The dashboard should display a badge or indicator for each device showing CFEngine server status.

2. **Port 5308 reachability** — can be checked via `tcp_open(ts_ip, 5308)` in `fleet_health.py`. Currently not scraped but the probe function exists. Add to `HEALTH_GATHER` or as a separate Mac-side probe.

3. **Connection tier status** — a compact 4-tier indicator per device showing:
   - ADB: ✅/❌
   - SSH: ✅/❌
   - CFEngine: ✅/❌
   - FIRERPA: ✅/❌

### Existing data the dashboard can use

- `just health` / `just firerpa-health` output, which already includes cfengine status
- `~/.config/stayturgid/logs/fleet-health.log` — parsed by `fleet_health.py`
- `~/.config/stayturgid/logs/firerpa-health.log` — parsed by `firerpa_health_monitor.py`
- `~/.config/stayturgid/devices.conf` — device mapping (alias, tailscale_ip, lan_ip, usb_serial)

## Known issues

1. **cf-runagent protocol version mismatch** (Mac 3.28.0 vs Termux 3.27.1):
   Returns "Unspecified server refusal" on bundle execution. TLS layer + key trust
   proven working. Fix: align versions or use `--protocol-version 2` flag.
   Once resolved, add `_try_cf_runagent_repair()` to `fleet_health_monitor.py`
   as Tier 3a fallback.

2. **Android seccomp blocks fork**: cf-serverd must be started with `-F` (foreground)
   flag. No fork is attempted. `nohup ... &` + PID file monitoring in boot loop
   provides the supervisor.

3. **cfengine package on Termux**: Currently in main repo (3.27.1). Added to
   Ansible `stayturgid_termux_packages` for fleet-wide deployment on next
   `just deploy`.
