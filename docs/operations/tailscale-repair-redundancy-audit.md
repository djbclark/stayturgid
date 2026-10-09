# Tailscale repair redundancy audit (issue #201)

Source-derived audit, 2026-10-09. Answers the first half of
[#201](https://github.com/djbclark/stayturgid/issues/201): what the native
agent and the Termux repair loop each do for Tailscale, where they overlap, and
what consolidation would cost. The issue's second half (watch a real boot and
compare timings) still needs a device and is listed under "Field verification"
below. No code was changed.

Context: [agent-apk-migration-candidates.md](agent-apk-migration-candidates.md)
("Tailscale repair (Termux copy) — Audit redundancy only").

## 1. The three implementations

Healing-registry IDs `TAILSCALE-VPN` and `TAILSCALE-ALWAYSON`
(`tests/healing_registry.json`) both list `termux_repair`, `native_agent` and
`ansible_deploy` as **must_cover**. So the redundancy is currently enforced by
the pre-flight test, not accidental.

| Aspect                                         | Native agent                                                                                                                                                   | Termux repair                                                                                                                              | Ansible deploy                                                                                                               |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Code                                           | `CatastrophicRepair.repairTailscale()` in `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/CatastrophicRepair.kt`, probes in `ComonitorProbes.kt` | `ensure_tailscale()` and `_tailscale_status()` in `device/termux/py/stayturgid_repair.py`                                                  | role `stayturgid.android_common.tailscale_vpn`                                                                               |
| Trigger                                        | `HostService.callComonitor()` sees `tailscale=down` or `tailscale_policy=down` in the agent STATUS line                                                        | Every repair pass (step 10 of `main()`), unconditionally                                                                                   | Fleet deploy                                                                                                                 |
| Cadence                                        | Once after the Shizuku bind succeeds (bind retried for up to 5 min after boot), then every 20 min plus a per-device stagger (`COMONTOR_INTERVAL_MS`)           | 30 s boot settle (`STAYTURGID_BOOT_SETTLE_SEC`), then every 300 s (`STAYTURGID_INTERVAL_SEC`), plus one pass after an ADB re-authorisation | On demand                                                                                                                    |
| Privilege                                      | uid 2000 via the Shizuku UserService, so it works on Fire OS and split-storage hosts                                                                           | Needs localhost:5555 adbd (`have_sh`); returns `unknown` and does nothing without it (PR #179)                                             | ADB from the Mac                                                                                                             |
| Policy written                                 | `always_on_vpn_app=com.tailscale.ipn`, `always_on_vpn_lockdown=0`, written on every call before probing                                                        | Same two settings, same hard-coded `0`                                                                                                     | `always_on_vpn_app`, and lockdown from `stayturgid_always_on_vpn_lockdown`; skipped when `stayturgid_always_on_vpn` is false |
| Runtime probe                                  | Tunnel interface (`tailscale0` or `tunN`) in `/proc/net/dev` and one ping to `controlplane.tailscale.com`                                                      | Same interface regex read through `sh_adb`, two pings                                                                                      | None                                                                                                                         |
| Reconnect                                      | `CONNECT_VPN` broadcast to `IPNReceiver`, then 4 polls at 2 s                                                                                                  | Same broadcast, then 3 polls at 2 s                                                                                                        | None                                                                                                                         |
| Never launches MainActivity                    | Yes (agent 0.9.8, #64)                                                                                                                                         | Yes (#199)                                                                                                                                 | n/a                                                                                                                          |
| Honors `device.json` `tailscaleEnabled: false` | **No.** `ComonitorProbes` skips only when the package is not installed                                                                                         | Yes, returns `skip`                                                                                                                        | n/a (`stayturgid_tailscale_enabled` only feeds `device.json`)                                                                |
| Failure signal                                 | `agent.log` line "tailscale still down after CONNECT_VPN" (picked up by `control/lib/fleet_health.py`)                                                         | `watchdog.log` ERR line, `rc=1`, counted by the on-device error-rate notifier                                                              | Task failure                                                                                                                 |
| Tests                                          | `ComonitorProbesTest.kt` covers the interface parser only; `repairTailscale()` itself has no unit test                                                         | `tests/python/test_stayturgid_repair.py` covers up, repaired, FAILED and the no-shell `unknown` case                                       | Module unit tests for `android_settings`                                                                                     |

## 2. What is duplicated

1. **The repair action is byte-for-byte the same idea in two languages.** Both
   copies write the same two secure settings, probe the same interface regex
   plus control-plane ping, send the same `CONNECT_VPN` broadcast to the same
   receiver, poll for a few seconds, and refuse to foreground Tailscale.
2. **The probe logic is duplicated** (`ComonitorProbes.probeTailscale` and
   `_tailscale_runtime_up`), with small drift: one ping versus two, 4 polls
   versus 3. The drift is harmless today but is the kind that grows.
3. **Failure reporting is duplicated.** A real outage on a shell-capable host
   produces both an agent-log failure line and a watchdog ERR line every cycle,
   so the Mac's device-log tail sees the same outage twice.

## 3. Which copy is authoritative

The migration audit calls the agent "primary". The code does not bear that
out on hosts that have a privileged shell:

1. **Termux fires first after boot.** Its first pass runs 30 s after the boot
   loop starts. The agent's first check waits for the Shizuku bind, which the
   agent itself retries for up to 5 minutes.
2. **Termux fires more often in steady state.** 5 minutes against the agent's
   20 minutes. On a shell-capable host the agent only acts if a drop happens
   and is still present at its next tick, after Termux has already had up to
   four chances.
3. **On Fire OS and split-storage hosts the agent is the only working copy.**
   Termux has no uid-2000 shell there and correctly reports `unknown`.

So the agent is the only copy that works everywhere, which makes it the right
**authoritative** implementation. On shell-capable hosts the Termux copy is
the **effective first responder** today, not a dormant backup.

## 4. Divergences worth fixing whatever the consolidation decision

1. **The agent ignores `tailscaleEnabled: false`.** On a device whose profile
   disables Tailscale but which still has the app installed, the agent probe
   reports `down`, and `repairTailscale()` then sets Tailscale as the always-on
   VPN and tries to connect it. The Termux copy skips such a device.
   Proposed fix: read `tailscaleEnabled` in `DeviceProfile` (it already
   regex-extracts `privilegedShellExpected` from the same file) and return
   `skip` from both Tailscale probes when it is false.
2. **Both device copies hard-code `always_on_vpn_lockdown=0` and ignore
   `stayturgid_always_on_vpn`.** Ansible makes both configurable. If a site
   ever sets lockdown to true, or turns always-on off, the device copies undo
   the deploy within one cycle. Proposed fix: render the two values into
   `device.json` (the template already carries `tailscaleEnabled`) and have
   both copies read them, defaulting to today's behaviour.
3. **`repairTailscale()` has no unit test.** Its branching is reachable only
   through Android process calls. The #64 handoff
   (`docs/operations/sessions/handoff-2026-07-28-issue-66-peer-marker-issue-64-tailscale-gate.md`)
   already suggested extracting a pure decision function; that remains the
   cheapest way to cover it.
4. **Stale variable.** `tailscale_activity` (`ansible/inventory/group_vars/all.yml`)
   is still rendered into `device.json` as `tailscaleActivity`, but nothing
   launches MainActivity any more (#64, #199). The same file's comment
   "Tailscale health checks in AutoJs6 watchdog" refers to the retired AutoJs6
   path. Both are documentation-level clean-ups.

## 5. Recommended consolidation

Do not delete the Termux copy yet. Thin it in this order, each step a separate
reviewable change:

1. **Fix divergences 1 and 2 above in both copies.** This is safe on its own and
   removes the only behavioural differences, so later steps change timing only.
2. **Decide the responder per host class, explicitly.** Recommended:
   - Fire OS / split-storage (`privilegedShellExpected: false`): agent only. This
     is already true in practice.
   - Shell-capable hosts: keep Termux as the fast detector and repairer, or
     shorten the agent's Tailscale check to match. The agent's 20-minute
     co-monitor cadence is the obstacle to making it sole owner. Running the
     cheap Tailscale probe on the 5-minute ping loop would remove it.
3. **Only after the field verification below shows the agent repairing within
   one Termux interval**, reduce the Termux copy to a probe that reports status
   and leaves repair to the agent, then drop `termux_repair` from the two
   healing-registry entries' `must_cover` (to `should_cover`).

### Risks

1. **Boot window.** The agent cannot act until the Shizuku bind succeeds. If
   Shizuku is slow or its authorisation dialog is unanswered, the agent does
   nothing while Termux, if it has a shell, still can. Removing the Termux copy
   loses that path.
2. **Agent outage.** A crashed or force-stopped agent FGS currently leaves Termux
   repairing Tailscale. After thinning, Tailscale recovery would depend on the
   agent being up, and Tailscale is also the Mac's way to reach the device to
   restart the agent.
3. **Registry contract.** `just test` fails if a `must_cover` mechanism loses its
   `@heals` tag, so step 3 must edit `tests/healing_registry.json` in the same
   commit.
4. **Duplicate alerting** is the main cost of keeping both. It is noise, not a
   correctness problem.

## 6. Field verification still required (the issue's ask)

On one shell-capable phone and one Fire OS tablet:

1. Reboot, then record the timestamps of the first Termux `STATUS` line in
   `watchdog.log`, the first agent `STATUS` line in `agent.log`, and the first
   `tailscale=up` in each.
2. With the device up, disconnect Tailscale from its notification and record
   which copy logs the reconnect first and how long the tunnel stays down.
3. On a host with `tailscaleEnabled: false` and Tailscale installed, confirm
   whether the agent rewrites `always_on_vpn_app` (divergence 1).

This needs device access and the operator's go-ahead, so it was not run during
the audit.
