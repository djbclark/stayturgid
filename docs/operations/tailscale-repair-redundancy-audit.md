# Tailscale repair redundancy audit (issue #201)

Source-derived audit, 2026-10-09 (ClaudeHelm night run; evening run added
sections 7 to 9 and the exact field-verification commands). Answers the first
half of [#201](https://github.com/djbclark/stayturgid/issues/201): what the
native agent and the Termux repair loop each do for Tailscale, where they
disagree, which should own what, and what consolidation would cost. The issue's
second half (watch a real boot and compare timings) still needs a device and is
listed under "Field verification" below with the commands to run. The only code
change is the no-risk constant consolidation in section 8.

Context: [agent-apk-migration-candidates.md](agent-apk-migration-candidates.md)
("Tailscale repair (Termux copy) — Audit redundancy only").

## 1. The three implementations

Healing-registry IDs `TAILSCALE-VPN` and `TAILSCALE-ALWAYSON`
(`tests/healing_registry.json`) both list `termux_repair`, `native_agent` and
`ansible_deploy` as **must_cover**. So the redundancy is currently enforced by
the pre-flight test, not accidental.

| Aspect                                         | Native agent                                                                                                                                                   | Termux repair                                                                                                                                                                                                                                                      | Ansible deploy                                                                                                               |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Code                                           | `CatastrophicRepair.repairTailscale()` in `device/native-agent/app/src/main/kotlin/org/stayturgid/agent/CatastrophicRepair.kt`, probes in `ComonitorProbes.kt` | `ensure_tailscale()` and `_tailscale_status()` in `device/termux/py/stayturgid_repair.py`                                                                                                                                                                          | role `stayturgid.android_common.tailscale_vpn`                                                                               |
| Trigger                                        | `HostService.callComonitor()` sees `tailscale=down` or `tailscale_policy=down` in the agent STATUS line                                                        | Every repair pass (step 10 of `main()`), unconditionally                                                                                                                                                                                                           | Fleet deploy                                                                                                                 |
| Cadence                                        | Once after the Shizuku bind succeeds (bind retried for up to 5 min after boot), then every 20 min plus a per-device stagger (`COMONTOR_INTERVAL_MS`)           | 30 s boot settle (`STAYTURGID_BOOT_SETTLE_SEC`), then every 900 s as deployed (`STAYTURGID_INTERVAL_SEC`, rendered from `stayturgid_interval_sec: 900`; `start_adb.py`'s 300 s default applies only when it is unset), plus one pass after an ADB re-authorisation | On demand                                                                                                                    |
| Privilege                                      | uid 2000 via the Shizuku UserService, so it works on Fire OS and split-storage hosts                                                                           | Needs localhost:5555 adbd (`have_sh`); returns `unknown` and does nothing without it (PR #179)                                                                                                                                                                     | ADB from the Mac                                                                                                             |
| Policy written                                 | `always_on_vpn_app=com.tailscale.ipn`, `always_on_vpn_lockdown=0`, written on every call before probing                                                        | Same two settings, same hard-coded `0`                                                                                                                                                                                                                             | `always_on_vpn_app`, and lockdown from `stayturgid_always_on_vpn_lockdown`; skipped when `stayturgid_always_on_vpn` is false |
| Runtime probe                                  | Tunnel interface (`tailscale0` or `tunN`) in `/proc/net/dev` and one ping to `controlplane.tailscale.com`                                                      | Same interface regex read through `sh_adb`, two pings                                                                                                                                                                                                              | None                                                                                                                         |
| Reconnect                                      | `CONNECT_VPN` broadcast to `IPNReceiver`, then 4 polls at 2 s                                                                                                  | Same broadcast, then 3 polls at 2 s                                                                                                                                                                                                                                | None                                                                                                                         |
| Never launches MainActivity                    | Yes (agent 0.9.8, #64)                                                                                                                                         | Yes (#199)                                                                                                                                                                                                                                                         | n/a                                                                                                                          |
| Honors `device.json` `tailscaleEnabled: false` | **No.** `ComonitorProbes` skips only when the package is not installed                                                                                         | Yes, returns `skip`                                                                                                                                                                                                                                                | n/a (`stayturgid_tailscale_enabled` only feeds `device.json`)                                                                |
| Failure signal                                 | `agent.log` line "tailscale still down after CONNECT_VPN" (picked up by `control/lib/fleet_health.py`)                                                         | `watchdog.log` ERR line, `rc=1`, counted by the on-device error-rate notifier                                                                                                                                                                                      | Task failure                                                                                                                 |
| Tests                                          | `ComonitorProbesTest.kt` covers the interface parser only; `repairTailscale()` itself has no unit test                                                         | `tests/python/test_stayturgid_repair.py` covers up, repaired, FAILED and the no-shell `unknown` case                                                                                                                                                               | Module unit tests for `android_settings`                                                                                     |

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
2. **Termux fires somewhat more often in steady state.** 15 minutes as
   deployed (`stayturgid_interval_sec: 900`) against the agent's 20 minutes
   plus stagger. On a shell-capable host the agent only acts if a drop happens
   and is still present at its next tick, after Termux has already had one or
   two chances. The lead is small, so the field timing below matters more
   than the nominal cadences.
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
     cheap Tailscale probe on the agent's 5-minute ping loop (`PING_INTERVAL_MS`),
     which is already faster than the 15-minute Termux loop, would remove it.
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

Needs a device and the operator's go-ahead, so it was not run. One
shell-capable phone first (test order s24, hd8, p7a), then one Fire OS tablet.
Announce the device use first. `H` is the inventory host, `S` its USB serial;
all reads are over USB so a Tailscale drop cannot take the observer with it.

```bash
H=s24; S=<usb-serial>
TERMUX_LOG=/sdcard/stayturgid/logs/watchdog.log   # Termux repair loop
AGENT_LOG=/sdcard/stayturgid/logs/agent.log       # native agent co-monitor
```

1. **Boot race.** `adb -s $S reboot`, wait for `adb -s $S wait-for-device`, then
   after ten minutes pull both logs (`adb -s $S pull $TERMUX_LOG`,
   `adb -s $S pull $AGENT_LOG`) and record, from the reboot time: the first
   Termux `STATUS` line, the first `[agent] STATUS` line, and the first
   `tailscale=up` in each. Also record the first Termux line that says
   "Tailscale runtime/policy restored" or "Tailscale still down", and the first
   `repairTailscale`/`tailscale restored` line from the agent, if either copy
   acted. Whichever copy acted first, and how long after boot, is the answer to
   the issue's question.
2. **Mid-day drop.** With the device up, disconnect Tailscale from its
   notification (or the app's toggle), note the time, and poll
   `adb -s $S shell "grep -oE '(tailscale0|tun[0-9]+)' /proc/net/dev | sort -u"`
   every 30 s until an interface is back. Then pull both logs again and record
   which copy logged the reconnect first (Termux "restored via" / agent
   "restored via CONNECT_VPN") and the total time the tunnel was down. Expect
   up to 15 min (Termux) or 20 min plus stagger (agent).
3. **Divergence 1 (agent ignores `tailscaleEnabled: false`).** Only on a host
   whose `device.json` has `"tailscaleEnabled": false` and Tailscale installed:
   `adb -s $S shell settings get secure always_on_vpn_app` before and after the
   agent's next co-monitor tick (watch `$AGENT_LOG`). If it changes to
   `com.tailscale.ipn`, the divergence is confirmed live.
4. **Fire OS.** Repeat step 1 on hd8 and confirm the Termux copy logs
   `unknown` for Tailscale (no uid-2000 shell) while the agent reports a real
   state.

Record the four results in a comment on #201; they decide between sections 5
and 7.

## 7. Which copy should own what (recommendation, reconciled)

Two readings of the same code were posted on #201 the night before this
section was written: the one above (agent authoritative, thin Termux in
stages) and a second comment (keep both until the agent checks Tailscale at
about the Termux cadence). They agree on every fact and differ only on
sequencing, so the recommendation is:

| Concern                                                          | Owner                                                                                           | Why                                                                                                                    |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Always-on policy (`always_on_vpn_app`, `always_on_vpn_lockdown`) | **Ansible** sets it; the device copies only re-assert what `device.json` says                   | One source of truth. Today both device copies hard-code lockdown `0` (divergence 2) and so override the deploy         |
| Runtime repair on Fire OS / split-storage                        | **Agent only**                                                                                  | Already true in practice: Termux has no uid-2000 shell and reports `unknown`                                           |
| Runtime repair on shell-capable hosts                            | **Agent**, once its Tailscale check runs on the 5-minute ping loop; **Termux stays** until then | The agent is the only copy that works everywhere, but today Termux is the faster responder (15 min vs 20 plus stagger) |
| Detection / fleet-health signal                                  | **Both**, always                                                                                | The Termux STATUS line is read by the Mac's fleet health; it costs nothing to keep after the repair action is removed  |
| Reconnect action after thinning                                  | Agent                                                                                           | Termux becomes probe-only (keep `_tailscale_status`, drop the `settings put` and the broadcast)                        |

Order of work, each its own reviewable change:

1. Render `stayturgid_always_on_vpn` and `stayturgid_always_on_vpn_lockdown`
   into `device.json` and have both device copies read them (divergence 2).
   Do this **only** after the #289 interlock has been verified on a device
   ([tailscale-lockdown-interlock.md](deep-dives/tailscale-lockdown-interlock.md)
   section 6) and with Tailscale key expiry disabled for fleet nodes, because
   it is what makes `lockdown=1` durable.
2. Make the agent honour `tailscaleEnabled: false` (divergence 1).
3. Run the agent's Tailscale probe on its 5-minute ping loop.
4. Run the field verification in section 6.
5. If step 4 shows the agent repairing within one Termux interval, make the
   Termux copy probe-only and move `termux_repair` from `must_cover` to
   `should_cover` on `TAILSCALE-VPN` and `TAILSCALE-ALWAYSON` in
   `tests/healing_registry.json` in the same commit.

Keep both until step 5. Nothing is deleted on the strength of code reading
alone.

## 8. No-risk consolidation done in this audit

1. `device/termux/py/stayturgid_repair.py`: the `CONNECT_VPN` broadcast action
   was the one Tailscale literal not held in a constant; it is now
   `TAILSCALE_CONNECT_ACTION`, the same name the agent uses
   (`CatastrophicRepair.TAILSCALE_CONNECT_ACTION`). Behaviour unchanged;
   `tests/python/test_stayturgid_repair.py` covers the broadcast.
2. `ansible/inventory/group_vars/all.yml`: the comment on
   `stayturgid_tailscale_enabled` still said "AutoJs6 watchdog"; it now names
   the Termux loop and notes that the agent ignores the flag (landed with the
   #289 commit).

Looked at and left alone:

1. `tailscale_activity` / `tailscaleActivity` in `device.json`: nothing reads
   it, but the template comment says the descriptive keys are kept on purpose
   so the file explains itself on the phone. Removing it is a decision, not
   dead-code cleanup.
2. The Kotlin side has `"com.tailscale.ipn"` as a literal in
   `CatastrophicRepair.repairTailscale()` and as a private
   `ComonitorProbes.TAILSCALE_PACKAGE`. Deduplicating needs a Gradle build to
   verify, and a build was already running on the machine (one at a time), so
   the two-line patch is queued, not applied.

## 9. Interaction with the #289 lockdown interlock

The Ansible role now refuses `always_on_vpn_lockdown=1` unless Tailscale is
authenticated and the management path is healthy, and backs off to `0` if the
path dies right after the write. The device copies then write `0` again on
their next cycle regardless. So until step 1 of section 7 lands, the fleet
has three writers of the same setting and only the device copies win. That
is safe (lockdown stays off) but it means the interlock cannot be verified
end-to-end for more than one cycle; the verification steps in the interlock
note account for it.
